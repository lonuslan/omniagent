"""
OmniAgent Studio — Windows Desktop Application.

Uses pywebview to create a native Windows window with a modern
HTML/CSS/JS dashboard backed by the Python orchestrator engine.
"""

from __future__ import annotations

import asyncio
import json
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
    """
    JS ↔ Python bridge exposed to the webview frontend.

    The frontend calls these methods via:  window.pywebview.api.methodName()
    """

    def __init__(self, window: webview.Window) -> None:
        self._window = window
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._running = False
        self._setup_registry()

    def _setup_registry(self) -> None:
        registry = AgentRegistry()
        for cls in [
            GeneralAgent,
            CodeGenAgent,
            CodeReviewAgent,
            DocWriterAgent,
            TestAgent,
        ]:
            temp = cls()
            registry.register(temp.descriptor, cls)
        self._registry = registry
        self._orchestrator = Orchestrator(registry)

    # ── API Methods (called from JS) ────────────────────────────────────

    def get_agents(self) -> str:
        """Return all registered agents as JSON."""
        if not self._registry:
            return "[]"
        agents = []
        for desc in self._registry.list_all():
            agents.append(
                {
                    "id": desc.id,
                    "name": desc.name,
                    "capabilities": [c.value for c in desc.capabilities],
                    "role": desc.role.value,
                    "provider": desc.provider,
                }
            )
        return json.dumps(agents)

    def get_workflows(self) -> str:
        """Return available workflow templates."""
        workflows = [
            {
                "name": "software_lifecycle",
                "description": "Full software development lifecycle",
                "stages": [
                    {"name": "需求确认", "emoji": "📋", "capabilities": ["general_purpose"]},
                    {"name": "需求分析", "emoji": "🔬", "capabilities": ["architecture_design"]},
                    {"name": "原型设计", "emoji": "🎨", "capabilities": ["ui_design"]},
                    {"name": "前端开发", "emoji": "💻", "capabilities": ["code_generation"]},
                    {"name": "后端开发", "emoji": "⚙️", "capabilities": ["code_generation"]},
                    {"name": "测试", "emoji": "🧪", "capabilities": ["testing"]},
                    {"name": "部署上线", "emoji": "🚀", "capabilities": ["deployment"]},
                ],
            },
            {
                "name": "video_production",
                "description": "End-to-end video production pipeline",
                "stages": [
                    {"name": "文案脚本", "emoji": "📝", "capabilities": ["copywriting"]},
                    {"name": "素材准备", "emoji": "📦", "capabilities": ["general_purpose"]},
                    {"name": "视频剪辑", "emoji": "✂️", "capabilities": ["video_editing"]},
                    {"name": "音频制作", "emoji": "🎵", "capabilities": ["audio_production"]},
                    {"name": "转场特效", "emoji": "✨", "capabilities": ["video_editing"]},
                    {"name": "审阅修改", "emoji": "👀", "capabilities": ["general_purpose"]},
                    {"name": "导出发布", "emoji": "🚀", "capabilities": ["video_editing"]},
                ],
            },
        ]
        return json.dumps(workflows)

    def run_demo(self) -> str:
        """Start the orchestration demo. Returns initial task info."""
        if self._running:
            return json.dumps({"status": "error", "message": "Demo already running"})

        self._running = True
        threading.Thread(target=self._run_demo_thread, daemon=True).start()
        return json.dumps({"status": "started", "message": "Demo started"})

    def get_status(self) -> str:
        return json.dumps({"running": self._running})

    # ── Demo Logic (runs in background thread) ────────────────────────

    def _run_demo_thread(self) -> None:
        """Run the orchestration demo and push events to the frontend."""
        try:
            self._emit_event("system", "Initializing OmniAgent orchestrator...", "system")
            time.sleep(0.4)

            if not self._registry or not self._orchestrator:
                self._running = False
                return

            # Register agents
            agents_info = []
            for desc in self._registry.list_all():
                caps = ", ".join(c.value for c in desc.capabilities[:2])
                agents_info.append(f"{desc.name} [{caps}]")
                self._emit_event("system", f"Registered: {desc.name} [{caps}]", "info")
                time.sleep(0.15)

            self._emit_event("system", f"Orchestrator ready. {len(agents_info)} agents.", "success")
            time.sleep(0.5)

            # Task analysis
            task = Task(
                id=str(uuid.uuid4()),
                title="Build a Full-Stack Todo App",
                description="React + FastAPI + PostgreSQL",
                domain="software",
                workflow_template="software_lifecycle",
            )

            self._emit_event("orchestrator", "Task received: Build a Full-Stack Todo App", "info")
            time.sleep(0.3)

            analyzer = TaskAnalyzer()
            analysis = analyzer.analyze(task)

            self._emit_event("orchestrator", "🔬 Analyzing task...", "thinking")
            time.sleep(0.5)
            self._emit_event(
                "orchestrator",
                f"Domain: {analysis['domain']} | Workflow: {analysis['suggested_workflow']}",
                "info",
            )
            time.sleep(0.3)

            # Decomposition
            self._emit_event("orchestrator", "🔄 Decomposing into stages...", "thinking")
            time.sleep(0.5)

            workflow = SoftwareLifecycleWorkflow()
            sub_tasks = workflow.generate_sub_tasks(task)

            self._emit_event(
                "orchestrator",
                f"Decomposed into {len(sub_tasks)} stages",
                "success",
            )

            # Initialize pipeline in frontend
            self._window.evaluate_js(f"initPipeline({len(sub_tasks)})")
            time.sleep(0.3)

            # Agent assignment
            agent_map = {
                0: "general-agent",
                1: "doc-writer-agent",
                2: "code-gen-agent",
                3: "code-gen-agent",
                4: "code-gen-agent",
                5: "test-agent",
                6: "general-agent",
            }

            stage_names = [s.name for s in workflow.stages]
            for i, st in enumerate(sub_tasks):
                best_id = agent_map.get(i, "general-agent")
                best = self._registry.get(best_id)
                if best:
                    st.assigned_agent = best.id
                    self._emit_event(
                        "orchestrator",
                        f"Stage {i + 1} '{stage_names[i]}' → {best.name}",
                        "info",
                    )
                    time.sleep(0.12)

            self._emit_event("system", "All stages assigned. Starting execution.", "success")
            time.sleep(0.3)

            # Execute stages
            self._emit_event("system", "⚡ Pipeline execution started", "system")

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
                self._window.evaluate_js(f"setAgentStatus('{agent_id}', 'running')")
                self._window.evaluate_js(f"setStageStatus({i}, 'running', '{agent_id}')")

                self._emit_event(agent_id, f"Starting: {stage_names[i]}", "thinking")
                time.sleep(1.0)  # Simulate work

                self._emit_event(agent_id, outputs[i], "success")
                self._window.evaluate_js(f"setStageStatus({i}, 'completed')")
                self._window.evaluate_js(f"setAgentStatus('{agent_id}', 'idle')")
                time.sleep(0.3)

            # Done
            self._emit_event("system", "🎉 Project completed! 7/7 stages done.", "success")
            self._emit_event("system", "Agents involved: 4 | All tests passing", "system")
            self._window.evaluate_js("demoComplete()")

        except Exception as e:
            self._emit_event("system", f"Error: {e}", "error")
        finally:
            self._running = False

    def _emit_event(self, source: str, message: str, level: str) -> None:
        """Push an event to the frontend via JS evaluation."""
        escaped = message.replace("\\", "\\\\").replace("'", "\\'")
        self._window.evaluate_js(f"addEvent('{source}', '{escaped}', '{level}')")


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    """Launch the OmniAgent Studio desktop window."""

    assets = get_assets_dir()
    html_path = assets / "index.html"

    if not html_path.exists():
        raise FileNotFoundError(f"GUI assets not found at {html_path}")

    html_content = html_path.read_text(encoding="utf-8")

    window = webview.create_window(
        title="OmniAgent Studio — Multi-Agent Orchestration",
        html=html_content,
        js_api=OmniAgentAPI(window),
        width=1280,
        height=860,
        min_size=(960, 600),
        resizable=True,
        easy_drag=False,
    )

    webview.start(debug=False, http_server=True)
