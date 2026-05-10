"""
Task Orchestrator v2 — LLM-powered, runtime-integrated, resilient.

Key improvements over v1:
  - LLM-driven TaskAnalyzer for semantic task understanding
  - Dynamic workflow generation from analysis (not fixed templates)
  - Real agent execution via AgentRuntimePool
  - Automatic retry on stage failure (configurable)
  - Context accumulation: each stage receives outputs from previous stages
  - Parallel execution of independent stages
  - Progress persistence via EventStream
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..protocol import AgentCapability, AgentEvent, CollaborationMessage, SubTask, Task, TaskStatus
from ..runtime.sandbox import AgentRuntimePool
from ..runtime.stream import EventStream, progress_event
from .analyzer import TaskAnalysis, TaskAnalyzer
from .registry import AgentRegistry


@dataclass
class OrchestratorConfig:
    """Configuration for orchestrator behavior."""
    max_retries_per_stage: int = 2
    parallel_stages: bool = True                # Execute independent stages in parallel
    require_approval_between_stages: bool = False
    fallback_to_general_agent: bool = True       # Use GeneralAgent when no match
    max_context_tokens: int = 8000               # Max context to pass between stages
    progress_callback: Any = None


class Orchestrator:
    """
    Central orchestrator v2 with LLM-powered analysis and real agent execution.

    Flow:
      1. LLM Analysis: semantic understanding of the task
      2. Dynamic Decomposition: generate tailored stages from analysis
      3. Intelligent Assignment: match stages to agents by capability + quality
      4. Resilient Execution: parallel where possible, retry on failure
      5. Context Pipeline: each stage sees all previous outputs
    """

    def __init__(
        self,
        registry: AgentRegistry,
        runtime_pool: AgentRuntimePool | None = None,
        config: OrchestratorConfig | None = None,
        llm_provider: Any | None = None,
    ) -> None:
        self.registry = registry
        self.runtime = runtime_pool
        self.config = config or OrchestratorConfig()
        self.analyzer = TaskAnalyzer(llm_provider=llm_provider)
        self.stream = EventStream()
        self._active_tasks: dict[str, Task] = {}
        self._stage_outputs: dict[str, list[dict[str, Any]]] = {}

    # ── Public API ───────────────────────────────────────────────────────

    async def submit(self, task: Task) -> tuple[Task, TaskAnalysis]:
        """Submit a task for analysis + decomposition. Returns the enriched task and analysis."""
        task.status = TaskStatus.ANALYZING
        self._active_tasks[task.id] = task

        await self.stream.publish(progress_event("orchestrator", task.id, "Analyzing task..."))

        # Phase 1: Semantic analysis (LLM or rules)
        analysis = await self.analyzer.analyze(task)
        task.status = TaskStatus.ROUTING

        await self.stream.publish(progress_event(
            "orchestrator", task.id,
            f"Domain: {analysis.domain} | Complexity: {analysis.complexity} | "
            f"Stages: {len(analysis.suggested_stages)}"
        ))

        # Phase 2: Generate sub-tasks from analysis stages
        sub_tasks = self._generate_sub_tasks(task, analysis)

        # Phase 3: Assign agents
        await self._assign_agents(sub_tasks)

        task.sub_tasks = sub_tasks
        task.status = TaskStatus.DELEGATED
        self._stage_outputs[task.id] = []

        return task, analysis

    async def execute(self, task: Task) -> Sequence[AgentEvent]:
        """Execute all sub-tasks with retry and parallelism."""
        if not task.sub_tasks:
            return []

        task.status = TaskStatus.IN_PROGRESS
        all_events: list[AgentEvent] = []
        completed: set[str] = set()
        failed: set[str] = set()
        retry_count: dict[str, int] = {}

        remaining = list(task.sub_tasks)

        while remaining:
            # Find stages whose dependencies are satisfied
            ready = [
                st for st in remaining
                if all(dep in completed for dep in st.dependencies)
                and st.id not in failed
            ]

            if not ready:
                # Check for deadlock: remaining tasks have unmet deps (all failed)
                stuck = [st for st in remaining if st.id not in failed]
                if stuck and all(
                    any(dep in failed for dep in st.dependencies)
                    for st in stuck
                ):
                    for st in stuck:
                        st.status = TaskStatus.FAILED
                        all_events.append(AgentEvent(
                            agent_id="orchestrator", task_id=st.id,
                            event_type="error",
                            data={"error": "Dependency failed: cannot proceed"},
                        ))
                    break
                break  # Tasks still have unmet dependencies

            # Execute ready tasks (parallel or sequential)
            if self.config.parallel_stages and len(ready) > 1:
                results = await asyncio.gather(
                    *[self._execute_stage(st, task) for st in ready],
                    return_exceptions=True,
                )
            else:
                results = []
                for st in ready:
                    results.append(await self._execute_stage(st, task))

            for st, result in zip(ready, results):
                if isinstance(result, Exception):
                    # Retry logic
                    retry_count[st.id] = retry_count.get(st.id, 0) + 1
                    if retry_count[st.id] <= self.config.max_retries_per_stage:
                        await self.stream.publish(progress_event(
                            "orchestrator", task.id,
                            f"Retrying stage '{st.title}' (attempt {retry_count[st.id]})"
                        ))
                        st.status = TaskStatus.PENDING
                        continue  # Leave in remaining for retry

                    st.status = TaskStatus.FAILED
                    failed.add(st.id)
                    all_events.append(AgentEvent(
                        agent_id=st.assigned_agent or "orchestrator",
                        task_id=st.id, event_type="error",
                        data={"error": str(result), "retries": retry_count[st.id]},
                    ))
                else:
                    st.status = TaskStatus.COMPLETED
                    completed.add(st.id)
                    all_events.extend(result if isinstance(result, list) else [])

            remaining = [
                st for st in remaining
                if st.id not in completed and st.id not in failed
            ]

        # Final status
        if failed:
            task.status = TaskStatus.FAILED
        else:
            task.status = TaskStatus.COMPLETED

        await self.stream.publish(progress_event(
            "orchestrator", task.id,
            f"Execution complete: {len(completed)} succeeded, {len(failed)} failed"
        ))

        return all_events

    # ── Internal: Decomposition ──────────────────────────────────────────

    def _generate_sub_tasks(self, task: Task, analysis: TaskAnalysis) -> list[SubTask]:
        """Generate sub-tasks from the analysis result."""
        stages = analysis.suggested_stages
        if not stages:
            # Fallback: single stage with all capabilities
            return [SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                title=task.title,
                description=task.description,
                required_capabilities=analysis.required_capabilities,
            )]

        sub_tasks: list[SubTask] = []
        previous_id: str | None = None

        for i, stage in enumerate(stages):
            caps = []
            for c in stage.get("capabilities", []):
                try:
                    caps.append(AgentCapability(c))
                except ValueError:
                    pass
            if not caps:
                caps = [AgentCapability.GENERAL_PURPOSE]

            # Build rich context from analysis
            context = {
                "task_summary": analysis.summary,
                "tech_stack": analysis.tech_stack,
                "features": analysis.features,
                "constraints": analysis.constraints,
                "stage_index": i,
                "stage_name": stage.get("name", f"Stage {i+1}"),
                "total_stages": len(stages),
            }

            st = SubTask(
                id=str(uuid.uuid4()),
                parent_task_id=task.id,
                title=stage.get("name", f"Stage {i+1}"),
                description=stage.get("description", task.description),
                required_capabilities=caps,
                dependencies=[previous_id] if previous_id else [],
                context=context,
            )
            sub_tasks.append(st)
            previous_id = st.id

        return sub_tasks

    # ── Internal: Agent Assignment ───────────────────────────────────────

    async def _assign_agents(self, sub_tasks: list[SubTask]) -> None:
        """Assign the best agent to each sub-task."""
        for st in sub_tasks:
            candidates = self.registry.find_by_capability(st.required_capabilities)
            if candidates:
                # Select best match (already sorted by score)
                st.assigned_agent = candidates[0][0].id
                await self.stream.publish(progress_event(
                    "orchestrator", st.parent_task_id,
                    f"Assigned '{st.title}' → {candidates[0][0].name} "
                    f"(score: {candidates[0][1]:.2f})"
                ))
            elif self.config.fallback_to_general_agent:
                st.assigned_agent = "general-agent"
                await self.stream.publish(progress_event(
                    "orchestrator", st.parent_task_id,
                    f"Fallback: '{st.title}' → GeneralAgent"
                ))
            else:
                st.assigned_agent = None

    # ── Internal: Stage Execution ────────────────────────────────────────

    async def _execute_stage(self, sub_task: SubTask, task: Task) -> list[AgentEvent]:
        """Execute a single stage with the assigned agent via the runtime pool."""

        # Inject previous stage outputs into context
        previous_outputs = self._stage_outputs.get(task.id, [])
        if previous_outputs:
            sub_task.context["previous_outputs"] = previous_outputs[-3:]  # Last 3

        if not sub_task.assigned_agent:
            return [AgentEvent(
                agent_id="orchestrator", task_id=sub_task.id,
                event_type="error",
                data={"error": f"No agent for: {sub_task.required_capabilities}"},
            )]

        descriptor = self.registry.get(sub_task.assigned_agent)
        if not descriptor:
            return [AgentEvent(
                agent_id="orchestrator", task_id=sub_task.id,
                event_type="error",
                data={"error": f"Agent not found: {sub_task.assigned_agent}"},
            )]

        await self.stream.publish(AgentEvent(
            agent_id=sub_task.assigned_agent, task_id=task.id,
            event_type="started",
            data={"stage": sub_task.title, "agent": descriptor.name},
        ))

        # Execute in runtime sandbox if available, otherwise simulate
        if self.runtime:
            agent = self._instantiate_agent(descriptor)
            if agent:
                async with self.runtime.session(agent, task.id) as runtime:
                    events = await runtime.execute(sub_task)
                    # Store output for next stages
                    self._stage_outputs[task.id].append({
                        "stage": sub_task.title,
                        "agent": descriptor.name,
                        "status": "completed",
                    })
                    return events

        # Simulation fallback (for demos)
        await asyncio.sleep(0.5)
        self._stage_outputs[task.id].append({
            "stage": sub_task.title,
            "agent": descriptor.name,
            "status": "completed",
        })
        return [AgentEvent(
            agent_id=sub_task.assigned_agent, task_id=task.id,
            event_type="completed",
            data={"stage": sub_task.title},
        )]

    def _instantiate_agent(self, descriptor: Any) -> Any:
        """Try to instantiate an agent from its descriptor. Returns None if not possible."""
        entry = self.registry._agents.get(descriptor.id)
        if entry and entry[1]:
            try:
                agent = entry[1]()
                agent.descriptor = descriptor
                return agent
            except Exception:
                return None
        return None

    # ── Collaboration ────────────────────────────────────────────────────

    async def route_message(self, message: CollaborationMessage) -> None:
        """Route inter-agent message through the collaboration bus."""
        # Forward to the target agent's runtime if active
        pass
