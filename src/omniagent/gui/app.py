"""
OmniAgent Studio — Windows Desktop Application.

pywebview native window + WebView2 rendering.
Background demo thread → event queue → JS polling → UI updates.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from pathlib import Path

import webview

from ..agents.builtin.generators import (
    CodeGenAgent, CodeReviewAgent, DocWriterAgent, GeneralAgent, TestAgent,
)
from ..core.analyzer import TaskAnalyzer
from ..core.orchestrator import Orchestrator, OrchestratorConfig
from ..core.registry import AgentRegistry
from ..core.workflow import SoftwareLifecycleWorkflow
from ..protocol import Task
from ..runtime.executor import ExecutionContext, ToolExecutor
from ..runtime.security import ExecutionMode, PermissionHandler, WorkspacePolicy
from ..tools.base import ToolRegistry


class OmniAgentAPI:
    """JS ↔ Python bridge. All methods called from the webview UI thread."""

    def __init__(self) -> None:
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._running = False
        self._events: queue.Queue = queue.Queue()
        self._mode: ExecutionMode = ExecutionMode.AGENT
        self._permissions = PermissionHandler(self._mode)
        self._tool_executor: ToolExecutor | None = None
        self._audit_log: list[dict] = []
        self._setup_registry()

    def _setup_registry(self) -> None:
        registry = AgentRegistry()
        for cls in [GeneralAgent, CodeGenAgent, CodeReviewAgent, DocWriterAgent, TestAgent]:
            temp = cls()
            registry.register(temp.descriptor, cls)
        self._registry = registry

        tool_reg = ToolRegistry()
        self._tool_executor = ToolExecutor(tool_reg, self._permissions)

        config = OrchestratorConfig(max_retries_per_stage=2, parallel_stages=True)
        self._orchestrator = Orchestrator(registry, config=config)

    # ── Mode & Security API ─────────────────────────────────────────────

    def get_mode(self) -> str:
        return json.dumps({
            "mode": self._mode.value,
            "label": {"plan": "Plan (只读)", "agent": "Agent (确认)", "auto": "Auto (全自动)"}[self._mode.value],
            "description": {
                "plan": "只读探索，不修改文件",
                "agent": "每步操作需确认",
                "auto": "全自动执行",
            }[self._mode.value],
        })

    def set_mode(self, mode: str) -> str:
        try:
            self._mode = ExecutionMode(mode)
            self._permissions.set_mode(self._mode)
            return json.dumps({"status": "ok", "mode": mode})
        except ValueError:
            return json.dumps({"status": "error", "message": f"Invalid mode: {mode}"})

    def get_audit_log(self) -> str:
        if self._tool_executor:
            records = self._tool_executor.get_audit_log()
            return json.dumps([{
                "tool": r.tool_name, "agent": r.agent_id,
                "args": {k: str(v)[:50] for k, v in r.args.items()},
                "result": r.result[:200], "error": r.is_error,
                "duration_ms": round(r.duration_ms, 1),
                "time": r.timestamp,
            } for r in records[-50:]])
        return "[]"

    def get_workspace_policy(self) -> str:
        policy = WorkspacePolicy()
        return json.dumps({
            "allowed_paths": policy.allowed_paths,
            "max_file_size_mb": policy.max_file_size_mb,
            "max_shell_timeout_sec": policy.max_shell_timeout_sec,
            "allow_network": policy.allow_network,
        })

    # ── Agent API ──────────────────────────────────────────────────────

    def get_agents(self) -> str:
        if not self._registry:
            return "[]"
        return json.dumps([{
            "id": d.id, "name": d.name,
            "capabilities": [c.value for c in d.capabilities],
            "role": d.role.value, "provider": d.provider,
        } for d in self._registry.list_all()])

    def get_workflows(self) -> str:
        return json.dumps([
            {"name": "software_lifecycle", "description": "Full software development lifecycle",
             "stages": [
                 {"name": "需求确认", "emoji": "📋", "capabilities": ["general_purpose"]},
                 {"name": "需求分析", "emoji": "🔬", "capabilities": ["architecture_design"]},
                 {"name": "原型设计", "emoji": "🎨", "capabilities": ["ui_design"]},
                 {"name": "前端开发", "emoji": "💻", "capabilities": ["code_generation"]},
                 {"name": "后端开发", "emoji": "⚙️", "capabilities": ["code_generation"]},
                 {"name": "测试", "emoji": "🧪", "capabilities": ["testing"]},
                 {"name": "部署上线", "emoji": "🚀", "capabilities": ["deployment"]},
             ]},
        ])

    # ── Demo API ────────────────────────────────────────────────────────

    def run_demo(self) -> str:
        if self._running:
            return json.dumps({"status": "error", "message": "Already running"})
        self._running = True
        self._events = queue.Queue()
        threading.Thread(target=self._demo_thread, daemon=True).start()
        return json.dumps({"status": "started"})

    def poll_events(self) -> str:
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return json.dumps(events)

    def get_status(self) -> str:
        return json.dumps({
            "running": self._running,
            "mode": self._mode.value,
            "agents": len(self._registry.list_all()) if self._registry else 0,
        })

    # ── Internals ───────────────────────────────────────────────────────

    def _emit(self, source: str, message: str, level: str = "info") -> None:
        self._events.put({"type": "event", "source": source, "message": message, "level": level})

    def _action(self, action: str, **kwargs) -> None:
        self._events.put({"type": "action", "action": action, **kwargs})

    def _demo_thread(self) -> None:
        try:
            self._run_demo()
        except Exception as e:
            self._emit("system", f"Error: {e}", "error")
        finally:
            self._running = False
            self._action("demo_complete")

    def _run_demo(self) -> None:
        self._emit("system", f"Mode: {self._mode.value.upper()} | Initializing orchestrator...", "system")
        time.sleep(0.3)

        if not self._registry:
            return

        for desc in self._registry.list_all():
            caps = ", ".join(c.value for c in desc.capabilities[:2])
            self._emit("system", f"Registered: {desc.name} [{caps}]", "info")
            time.sleep(0.08)

        self._emit("system", f"Orchestrator ready. 5 agents. Retry: {self._orchestrator.config.max_retries_per_stage}x", "success")
        time.sleep(0.4)

        task = Task(
            id=str(uuid.uuid4()),
            title="Build a Full-Stack Todo App",
            description="React + FastAPI + PostgreSQL",
            domain="software",
        )

        analyzer = TaskAnalyzer()
        analysis = analyzer.analyze_sync(task)

        self._emit("orchestrator", f"Task received: {task.title}", "info")
        time.sleep(0.3)
        self._emit("orchestrator", f"Domain: {analysis.domain} | Complexity: {analysis.complexity}", "info")
        self._emit("orchestrator", f"Tech: {', '.join(analysis.tech_stack) or 'React, FastAPI, PostgreSQL'}", "info")
        time.sleep(0.3)

        if analysis.risks:
            self._emit("orchestrator", f"Risks identified: {', '.join(analysis.risks[:3])}", "warning")
        time.sleep(0.2)

        # Use dynamic stages from analysis or fallback to workflow
        if analysis.suggested_stages:
            stages = analysis.suggested_stages
            self._action("init_pipeline", count=len(stages), stages=stages)
        else:
            workflow = SoftwareLifecycleWorkflow()
            sub_tasks = workflow.generate_sub_tasks(task)
            stages = [{"name": s.name, "description": s.description, "capabilities": [c.value for c in s.required_capabilities]} for s in workflow.stages]
            self._action("init_pipeline", count=len(stages), stages=stages)

        time.sleep(0.3)

        stage_names = [s["name"] for s in stages]
        self._emit("orchestrator", f"Decomposed into {len(stages)} stages", "success")
        time.sleep(0.3)

        # Assign agents
        agent_map = {0: "general-agent", 1: "doc-writer-agent", 2: "code-gen-agent",
                     3: "code-gen-agent", 4: "code-gen-agent", 5: "test-agent", 6: "general-agent"}
        for i, s in enumerate(stages):
            aid = agent_map.get(i, "general-agent")
            agent = self._registry.get(aid) if self._registry else None
            name = agent.name if agent else aid
            self._emit("orchestrator", f"Stage {i+1} '{stage_names[i]}' → {name}", "info")
            time.sleep(0.08)

        self._emit("system", "All stages assigned. Starting execution.", "success")
        time.sleep(0.3)

        outputs = [
            "Analyzed project scope and feature requirements",
            "Generated technical specification document",
            "Designed UI wireframes and component tree",
            "Created React components with TypeScript types",
            "Built FastAPI endpoints with PostgreSQL schema",
            "Wrote test suites — 24 unit tests, 8 integration tests",
            "Generated Docker deployment configurations",
        ]

        for i, s in enumerate(stages):
            aid = agent_map.get(i, "general-agent")
            self._action("stage_update", index=i, status="running", agent=aid)
            self._emit(aid, f"Starting: {stage_names[i]}", "thinking")
            time.sleep(0.8)

            # Simulate permission check in AGENT mode
            if self._mode == ExecutionMode.AGENT and i >= 2:
                self._emit("permission", f"Approval: write file (stage {i+1})", "warning")
                time.sleep(0.3)

            self._emit(aid, outputs[min(i, len(outputs)-1)], "success")
            self._action("stage_update", index=i, status="completed")
            time.sleep(0.15)

        self._emit("system", f"Project completed! {len(stages)}/{len(stages)} stages done.", "success")

        # Add mock audit record
        if self._tool_executor:
            self._audit_log.append({
                "tool": "write", "agent": "code-gen-agent",
                "args": {"file_path": "src/App.tsx", "content": "..."},
                "result": "File written successfully", "error": False,
                "duration_ms": 12.3, "time": time.time(),
            })

        self._emit("system", f"Mode '{self._mode.value}' completed. Agents: 4 | All tests passing", "system")


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    assets = get_assets_dir()
    html_path = assets / "index.html"
    if not html_path.exists():
        raise FileNotFoundError(f"GUI assets not found at {html_path}")

    api = OmniAgentAPI()
    webview.create_window(
        title="OmniAgent Studio — Multi-Agent Orchestration",
        html=html_path.read_text(encoding="utf-8"),
        js_api=api,
        width=1280, height=860,
        min_size=(960, 600),
        resizable=True,
    )
    webview.start(debug=False, http_server=True)
