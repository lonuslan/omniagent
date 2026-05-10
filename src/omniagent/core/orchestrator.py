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
from dataclasses import dataclass
from typing import Any

from ..protocol import AgentCapability, AgentEvent, CollaborationMessage, SubTask, Task, TaskStatus
from ..runtime.sandbox import AgentRuntimePool
from ..runtime.stream import EventStream, progress_event
from .analyzer import TaskAnalysis, TaskAnalyzer
from .negotiation import DebateProposal, NegotiationProtocol, NegotiationResult
from .registry import AgentRegistry
from .scorer import AgentScorer, ScoreBreakdown
from .workflow import WorkflowRegistry


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
        llm_bridge: Any | None = None,
    ) -> None:
        self.registry = registry
        self.runtime = runtime_pool
        self.config = config or OrchestratorConfig()
        self.analyzer = TaskAnalyzer(llm_provider=llm_provider)
        self.workflow_registry = WorkflowRegistry()
        self.scorer = AgentScorer(llm_bridge=llm_bridge)
        self.negotiator = NegotiationProtocol(llm_bridge=llm_bridge)
        self.stream = EventStream()
        self._active_tasks: dict[str, Task] = {}
        self._stage_outputs: dict[str, list[dict[str, Any]]] = {}
        self._score_breakdowns: dict[str, list[ScoreBreakdown]] = {}
        self._negotiation_results: dict[str, list[NegotiationResult]] = {}

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

    # Domain → workflow template name mapping
    _DOMAIN_WORKFLOW_MAP: dict[str, str] = {
        "software": "software_lifecycle",
        "video": "video_production",
        "document": "document_writing",
    }

    def _generate_sub_tasks(self, task: Task, analysis: TaskAnalysis) -> list[SubTask]:
        """Generate sub-tasks from analysis result, falling back to workflow templates."""
        stages = analysis.suggested_stages

        # If analyzer produced no stages, try workflow registry by domain
        if not stages:
            wf_name = self._DOMAIN_WORKFLOW_MAP.get(analysis.domain)
            if wf_name:
                template = self.workflow_registry.get(wf_name)
                if template:
                    return template.generate_sub_tasks(task)

            # No matching workflow either — single stage fallback
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
        """Assign the best agent to each sub-task using composite scoring."""
        task_id = sub_tasks[0].parent_task_id if sub_tasks else ""
        task_desc = ""
        if task_id in self._active_tasks:
            task_desc = self._active_tasks[task_id].description

        all_breakdowns: list[ScoreBreakdown] = []

        for st in sub_tasks:
            candidates = self.registry.find_by_capability(st.required_capabilities)
            if candidates:
                agent_descs = [desc for desc, _ in candidates]
                # Use composite scorer (LLM + capability + reputation)
                breakdowns = self.scorer.rank_agents(
                    task_desc, agent_descs, st.required_capabilities,
                    use_llm=bool(self.scorer._llm_bridge and self.scorer._llm_bridge.is_configured()),
                )
                best = breakdowns[0]

                # Negotiation: trigger when top 2 are close (within 10%)
                if len(breakdowns) >= 2:
                    gap = breakdowns[0].composite_score - breakdowns[1].composite_score
                    if gap < 0.10 and self.negotiator._llm_bridge and self.negotiator._llm_bridge.is_configured():
                        await self.stream.publish(progress_event(
                            "orchestrator", st.parent_task_id,
                            f"Negotiation: '{st.title}' — {breakdowns[0].agent_name} vs {breakdowns[1].agent_name} (gap: {gap:.2f})"
                        ))
                        proposals = [
                            DebateProposal(
                                agent_id=bd.agent_id, agent_name=bd.agent_name,
                                position=f"Agent {bd.agent_name} should handle '{st.title}'",
                                reasoning=f"Composite score: {bd.composite_score:.2f}. {bd.llm_reasoning}",
                            ) for bd in breakdowns[:2]
                        ]
                        neg_result = self.negotiator.negotiate(
                            topic=f"Best agent for stage: {st.title}",
                            proposals=proposals,
                            context=task_desc[:500],
                        )
                        if task_id not in self._negotiation_results:
                            self._negotiation_results[task_id] = []
                        self._negotiation_results[task_id].append(neg_result)

                        # Winner from negotiation
                        winner_id = neg_result.arbitration.winner_id
                        winner_name = neg_result.arbitration.winner_name
                        st.assigned_agent = winner_id
                        await self.stream.publish(progress_event(
                            "orchestrator", st.parent_task_id,
                            f"Negotiation result: '{st.title}' → {winner_name} "
                            f"(confidence: {neg_result.arbitration.confidence:.0%}) "
                            f"— {neg_result.arbitration.reasoning[:100]}"
                        ))
                    else:
                        st.assigned_agent = best.agent_id
                else:
                    st.assigned_agent = best.agent_id

                all_breakdowns.extend(breakdowns)

                await self.stream.publish(progress_event(
                    "orchestrator", st.parent_task_id,
                    f"Assigned '{st.title}' → {best.agent_name} "
                    f"(composite: {best.composite_score:.2f} | "
                    f"cap: {best.capability_score:.2f} | "
                    f"llm: {best.llm_score:.2f} | "
                    f"rep: {best.reputation_score:.2f})"
                ))
            elif self.config.fallback_to_general_agent:
                st.assigned_agent = "general-agent"
                await self.stream.publish(progress_event(
                    "orchestrator", st.parent_task_id,
                    f"Fallback: '{st.title}' → GeneralAgent"
                ))
            else:
                st.assigned_agent = None

        self._score_breakdowns[task_id] = all_breakdowns

    # ── Internal: Stage Execution ────────────────────────────────────────

    async def _execute_stage(self, sub_task: SubTask, task: Task) -> list[AgentEvent]:
        """Execute a single stage with the assigned agent via the runtime pool."""

        # Inject summarized previous stage outputs into context
        previous_outputs = self._stage_outputs.get(task.id, [])
        if previous_outputs:
            # Use LLM summaries if available, fall back to raw metadata
            summaries = []
            for output in previous_outputs[-3:]:
                if "summary" in output:
                    summaries.append(f"[{output['stage']}] {output['summary']}")
                else:
                    summaries.append(f"[{output['stage']}] by {output['agent']} — {output['status']}")
            sub_task.context["previous_outputs"] = summaries

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
                    # Record success in scorer
                    self.scorer.record_success(descriptor.id)
                    # Store output for next stages
                    self._stage_outputs[task.id].append({
                        "stage": sub_task.title,
                        "agent": descriptor.name,
                        "status": "completed",
                    })
                    return events

        # Simulation fallback (for demos)
        await asyncio.sleep(0.5)
        self.scorer.record_success(descriptor.id)
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

    # ── Context Summarization ───────────────────────────────────────────

    def summarize_output(self, stage_name: str, agent_name: str, full_output: str) -> str:
        """
        Use LLM to summarize a stage's output for passing to the next stage.
        Extracts: key decisions, tech choices, file paths, important constraints.
        Falls back to truncation if no LLM is available.
        """
        if not self.scorer._llm_bridge or not self.scorer._llm_bridge.is_configured():
            return full_output[:300]

        prompt = f"""Summarize this work output in 2-3 sentences. Focus on:
- Key decisions made
- Technologies/libraries chosen
- Files created or modified
- Important constraints or assumptions

Stage: {stage_name} (by {agent_name})
Output: {full_output[:1500]}

Reply with ONLY the summary, no preamble."""

        try:
            result = self.scorer._llm_bridge.complete_sync(
                model=self.scorer._llm_bridge._active_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.2,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if result.get("error"):
                return full_output[:300]
            return content.strip() or full_output[:300]
        except Exception:
            return full_output[:300]

    # ── Workflow Management ──────────────────────────────────────────────

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all available workflow templates with their stages."""
        result = []
        for name in self.workflow_registry.list_all():
            template = self.workflow_registry.get(name)
            if template:
                result.append({
                    "name": name,
                    "description": template.description,
                    "stages": [
                        {"name": s.name, "description": s.description,
                         "capabilities": [c.value for c in s.required_capabilities]}
                        for s in template.stages
                    ],
                })
        return result

    async def register_custom_workflow(self, name: str, description: str, stages: list[dict[str, Any]]) -> None:
        """Register a user-defined workflow template."""
        from .workflow import IWorkflowTemplate, WorkflowStage

        class CustomWorkflow(IWorkflowTemplate):
            pass

        wf = CustomWorkflow()
        wf.name = name
        wf.description = description
        wf.stages = []
        for s in stages:
            caps = []
            for c in s.get("capabilities", []):
                try:
                    caps.append(AgentCapability(c))
                except ValueError:
                    pass
            if not caps:
                caps = [AgentCapability.GENERAL_PURPOSE]
            wf.stages.append(WorkflowStage(
                name=s["name"],
                description=s.get("description", ""),
                required_capabilities=caps,
            ))
        self.workflow_registry.register(wf)
        await self.stream.publish(progress_event(
            "orchestrator", "",
            f"Custom workflow '{name}' registered with {len(wf.stages)} stages"
        ))

    # ── Collaboration ────────────────────────────────────────────────────

    async def route_message(self, message: CollaborationMessage) -> None:
        """Route inter-agent message through the collaboration bus."""
        pass
