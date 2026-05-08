"""
OmniAgent Studio — Windows Desktop Application.

Uses pywebview for native Windows window + WebView2 rendering.
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
    CodeGenAgent,
    CodeReviewAgent,
    DocWriterAgent,
    GeneralAgent,
    TestAgent,
)
from ..core.orchestrator import Orchestrator, TaskAnalyzer
from ..core.registry import AgentRegistry
from ..core.workflow import SoftwareLifecycleWorkflow
from ..protocol import Task


class OmniAgentAPI:
    """JS ↔ Python bridge. All methods are called from the webview UI thread."""

    def __init__(self) -> None:
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._running = False
        self._events: queue.Queue = queue.Queue()
        self._setup_registry()

    def _setup_registry(self) -> None:
        registry = AgentRegistry()
        for cls in [GeneralAgent, CodeGenAgent, CodeReviewAgent, DocWriterAgent, TestAgent]:
            temp = cls()
            registry.register(temp.descriptor, cls)
        self._registry = registry
        self._orchestrator = Orchestrator(registry)

    # ── API called from JS ──────────────────────────────────────────────

    def get_agents(self) -> str:
        if not self._registry:
            return "[]"
        agents = []
        for desc in self._registry.list_all():
            agents.append({
                "id": desc.id,
                "name": desc.name,
                "capabilities": [c.value for c in desc.capabilities],
                "role": desc.role.value,
            })
        return json.dumps(agents)

    def run_demo(self) -> str:
        if self._running:
            return json.dumps({"status": "error", "message": "Already running"})
        self._running = True
        self._events = queue.Queue()
        threading.Thread(target=self._demo_thread, daemon=True).start()
        return json.dumps({"status": "started"})

    def poll_events(self) -> str:
        """Called by JS every ~200ms. Returns all queued events as JSON array."""
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return json.dumps(events)

    def get_status(self) -> str:
        return json.dumps({"running": self._running})

    # ── Event helpers (called from demo thread) ─────────────────────────

    def _emit(self, source: str, message: str, level: str = "info") -> None:
        self._events.put({"type": "event", "source": source, "message": message, "level": level})

    def _action(self, action: str, **kwargs) -> None:
        self._events.put({"type": "action", "action": action, **kwargs})

    # ── Demo thread ─────────────────────────────────────────────────────

    def _demo_thread(self) -> None:
        try:
            self._run_demo()
        except Exception as e:
            self._emit("system", f"Error: {e}", "error")
        finally:
            self._running = False
            self._action("demo_complete")

    def _run_demo(self) -> None:
        self._emit("system", "Initializing OmniAgent orchestrator...", "system")
        time.sleep(0.3)

        if not self._registry:
            return

        for desc in self._registry.list_all():
            caps = ", ".join(c.value for c in desc.capabilities[:2])
            self._emit("system", f"Registered: {desc.name} [{caps}]", "info")
            time.sleep(0.1)

        self._emit("system", "Orchestrator ready. 5 agents.", "success")
        time.sleep(0.4)

        # Task analysis
        self._emit("orchestrator", "Task received: Build a Full-Stack Todo App", "info")
        time.sleep(0.3)

        task = Task(
            id=str(uuid.uuid4()),
            title="Build a Full-Stack Todo App",
            description="React + FastAPI + PostgreSQL",
            domain="software",
            workflow_template="software_lifecycle",
        )

        analyzer = TaskAnalyzer()
        analysis = analyzer.analyze(task)

        self._emit("orchestrator", "Analyzing task...", "thinking")
        time.sleep(0.5)
        self._emit("orchestrator", f"Domain: {analysis['domain']} | Workflow: software_lifecycle", "info")

        # Decomposition
        self._emit("orchestrator", "Decomposing into stages...", "thinking")
        time.sleep(0.4)

        workflow = SoftwareLifecycleWorkflow()
        sub_tasks = workflow.generate_sub_tasks(task)
        self._emit("orchestrator", f"Decomposed into {len(sub_tasks)} stages", "success")

        self._action("init_pipeline", count=len(sub_tasks))
        time.sleep(0.3)

        # Agent assignment
        agent_map = {0: "general-agent", 1: "doc-writer-agent", 2: "code-gen-agent",
                     3: "code-gen-agent", 4: "code-gen-agent", 5: "test-agent", 6: "general-agent"}
        stage_names = [s.name for s in workflow.stages]

        for i, st in enumerate(sub_tasks):
            best_id = agent_map.get(i, "general-agent")
            best = self._registry.get(best_id)
            if best:
                st.assigned_agent = best.id
                self._emit("orchestrator", f"Stage {i+1} '{stage_names[i]}' → {best.name}", "info")
                time.sleep(0.1)

        self._emit("system", "All stages assigned. Starting execution.", "success")
        time.sleep(0.3)
        self._emit("system", "Pipeline execution started", "system")

        outputs = [
            "Analyzed project scope and feature requirements",
            "Generated technical specification document",
            "Designed UI wireframes and component tree",
            "Created React components with TypeScript types",
            "Built FastAPI endpoints with PostgreSQL schema",
            "Wrote test suites — 24 unit tests, 8 integration tests",
            "Generated Docker deployment configurations",
        ]

        for i, st in enumerate(sub_tasks):
            agent_id = st.assigned_agent or "general-agent"
            self._action("stage_update", index=i, status="running", agent=agent_id)

            self._emit(agent_id, f"Starting: {stage_names[i]}", "thinking")
            time.sleep(1.0)

            self._emit(agent_id, outputs[i], "success")
            self._action("stage_update", index=i, status="completed")
            time.sleep(0.2)

        self._emit("system", "Project completed! 7/7 stages done.", "success")
        self._emit("system", "Agents involved: 4 | All tests passing", "system")


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    assets = get_assets_dir()
    html_path = assets / "index.html"
    if not html_path.exists():
        raise FileNotFoundError(f"GUI assets not found at {html_path}")

    html_content = html_path.read_text(encoding="utf-8")
    api = OmniAgentAPI()

    webview.create_window(
        title="OmniAgent Studio — Multi-Agent Orchestration",
        html=html_content,
        js_api=api,
        width=1280,
        height=860,
        min_size=(960, 600),
        resizable=True,
    )

    webview.start(debug=False, http_server=True)
