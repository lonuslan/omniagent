"""
OmniAgent Studio — Windows Desktop Application.
"""

from __future__ import annotations

import json, queue, threading, time, uuid
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
from ..runtime.security import ExecutionMode, PermissionHandler, WorkspacePolicy
from ..runtime.executor import ToolExecutor
from ..tools.base import ToolRegistry


# ── Built-in model definitions ──────────────────────────────────────────

BUILTIN_MODELS = [
    {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "deepseek",
     "base_url": "https://api.deepseek.com/v1", "context": "1M tokens", "pricing": "$0.44/$0.87 per 1M"},
    {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "deepseek",
     "base_url": "https://api.deepseek.com/v1", "context": "1M tokens", "pricing": "$0.14/$0.28 per 1M"},
    {"id": "mimo-general-v2", "name": "MiMo General V2", "provider": "mimo",
     "base_url": "https://api.xiaomimimo.com/v1", "context": "128K tokens", "pricing": "Free tier available"},
    {"id": "claude-opus-4-7", "name": "Claude Opus 4.7", "provider": "anthropic",
     "base_url": "https://api.anthropic.com/v1", "context": "200K tokens", "pricing": "$15/$75 per 1M"},
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic",
     "base_url": "https://api.anthropic.com/v1", "context": "200K tokens", "pricing": "$3/$15 per 1M"},
    {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "anthropic",
     "base_url": "https://api.anthropic.com/v1", "context": "200K tokens", "pricing": "$1/$5 per 1M"},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai",
     "base_url": "https://api.openai.com/v1", "context": "128K tokens", "pricing": "$2.50/$10 per 1M"},
    {"id": "gpt-4.5", "name": "GPT-4.5", "provider": "openai",
     "base_url": "https://api.openai.com/v1", "context": "128K tokens", "pricing": "$75/$150 per 1M"},
    {"id": "qwen-max", "name": "通义千问 Max", "provider": "qwen",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "context": "128K tokens", "pricing": "¥0.04/1K"},
    {"id": "qwen-plus", "name": "通义千问 Plus", "provider": "qwen",
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "context": "128K tokens", "pricing": "¥0.02/1K"},
]


class OmniAgentAPI:
    """JS ↔ Python bridge."""

    def __init__(self) -> None:
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._running = False
        self._events: queue.Queue = queue.Queue()
        self._mode: ExecutionMode = ExecutionMode.AGENT
        self._permissions = PermissionHandler(self._mode)
        self._tool_executor: ToolExecutor | None = None
        self._model_configs: dict[str, dict] = {}  # model_id → {api_key, base_url}
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

    # ── Mode ────────────────────────────────────────────────────────────

    def get_mode(self) -> str:
        return json.dumps({"mode": self._mode.value})

    def set_mode(self, mode: str) -> str:
        try:
            self._mode = ExecutionMode(mode)
            self._permissions.set_mode(self._mode)
            return json.dumps({"status": "ok"})
        except ValueError:
            return json.dumps({"status": "error"})

    # ── Model Config ────────────────────────────────────────────────────

    def get_models(self) -> str:
        """Return built-in model list with saved configs."""
        return json.dumps([{
            **m,
            "configured": m["id"] in self._model_configs,
            "has_key": bool(self._model_configs.get(m["id"], {}).get("api_key")),
        } for m in BUILTIN_MODELS])

    def save_model_config(self, model_id: str, api_key: str, base_url: str = "") -> str:
        cfg = {"api_key": api_key}
        if base_url:
            cfg["base_url"] = base_url
        self._model_configs[model_id] = cfg
        return json.dumps({"status": "ok"})

    def test_model_connection(self, model_id: str) -> str:
        cfg = self._model_configs.get(model_id)
        if not cfg or not cfg.get("api_key"):
            return json.dumps({"status": "error", "message": "请先配置 API Key"})
        model = next((m for m in BUILTIN_MODELS if m["id"] == model_id), None)
        if not model:
            return json.dumps({"status": "error", "message": "未知模型"})

        try:
            import httpx, asyncio
            url = cfg.get("base_url", model["base_url"]).rstrip("/") + "/chat/completions"
            is_anthropic = "anthropic" in url
            headers = {"Content-Type": "application/json"}
            if is_anthropic:
                headers["x-api-key"] = cfg["api_key"]
                headers["anthropic-version"] = "2023-06-01"
                body = {"model": model_id, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
                test_url = url.replace("/chat/completions", "/messages")
            else:
                headers["Authorization"] = f"Bearer {cfg['api_key']}"
                body = {"model": model_id, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
                test_url = url

            client = httpx.Client(timeout=15)
            resp = client.post(test_url, json=body, headers=headers)
            client.close()

            if resp.status_code in (200, 201):
                data = resp.json()
                content = ""
                if is_anthropic:
                    content = data.get("content", [{}])[0].get("text", "") if data.get("content") else ""
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return json.dumps({"status": "ok", "message": f"连接成功! 响应: {content[:60]}", "latency_ms": round(resp.elapsed.total_seconds() * 1000)})
            else:
                err = resp.json() if resp.text else {}
                msg = err.get("error", {}).get("message", "") or resp.text[:120]
                return json.dumps({"status": "error", "message": f"API 错误 ({resp.status_code}): {msg}"})
        except Exception as e:
            return json.dumps({"status": "error", "message": f"连接失败: {str(e)[:120]}"})

    def get_model_usage(self, model_id: str) -> str:
        cfg = self._model_configs.get(model_id)
        if not cfg:
            return json.dumps({"status": "error", "message": "未配置"})
        return json.dumps({
            "status": "ok",
            "model": model_id,
            "usage": {
                "total_requests": 0, "total_input_tokens": 0, "total_output_tokens": 0,
                "estimated_cost": "$0.00",
                "note": "用量统计将在首次 API 调用后更新"
            }
        })

    # ── Agents ──────────────────────────────────────────────────────────

    def get_agents(self) -> str:
        if not self._registry: return "[]"
        return json.dumps([{
            "id": d.id, "name": d.name,
            "capabilities": [c.value for c in d.capabilities],
            "role": d.role.value, "provider": d.provider,
        } for d in self._registry.list_all()])

    def get_audit_log(self) -> str:
        if self._tool_executor:
            records = self._tool_executor.get_audit_log()
            return json.dumps([{
                "tool": r.tool_name, "agent": r.agent_id,
                "args": {k: str(v)[:50] for k, v in r.args.items()},
                "result": r.result[:200], "error": r.is_error,
                "duration_ms": round(r.duration_ms, 1), "time": r.timestamp,
            } for r in records[-50:]])
        return "[]"

    # ── Demo ────────────────────────────────────────────────────────────

    def run_demo(self) -> str:
        if self._running: return json.dumps({"status": "error", "message": "Already running"})
        self._running = True; self._events = queue.Queue()
        threading.Thread(target=self._demo_thread, daemon=True).start()
        return json.dumps({"status": "started"})

    def poll_events(self) -> str:
        events = []
        while True:
            try: events.append(self._events.get_nowait())
            except queue.Empty: break
        return json.dumps(events)

    def get_status(self) -> str:
        return json.dumps({"running": self._running, "mode": self._mode.value,
                           "agents": len(self._registry.list_all()) if self._registry else 0})

    def _emit(self, source, message, level="info"):
        self._events.put({"type": "event", "source": source, "message": message, "level": level})

    def _action(self, action, **kw):
        self._events.put({"type": "action", "action": action, **kw})

    def _demo_thread(self):
        try: self._run_demo()
        except Exception as e: self._emit("system", f"Error: {e}", "error")
        finally: self._running = False; self._action("demo_complete")

    def _run_demo(self):
        self._emit("system", f"Mode: {self._mode.value.upper()} | Orchestrator starting...", "system")
        time.sleep(0.3)
        for desc in (self._registry or AgentRegistry()).list_all():
            self._emit("system", f"Registered: {desc.name}", "info"); time.sleep(0.06)
        self._emit("system", "Orchestrator ready. 5 agents.", "success"); time.sleep(0.3)

        task = Task(id=str(uuid.uuid4()), title="Build a Full-Stack Todo App",
                    description="React + FastAPI + PostgreSQL", domain="software")
        analysis = TaskAnalyzer().analyze_sync(task)
        self._emit("orchestrator", f"Task: {task.title}", "info"); time.sleep(0.2)
        self._emit("orchestrator", f"Domain: {analysis.domain} | Complexity: {analysis.complexity}", "info")

        stages = analysis.suggested_stages or [
            {"name": "需求确认", "emoji": "📋", "capabilities": ["general_purpose"]},
            {"name": "需求分析", "emoji": "🔬", "capabilities": ["architecture_design"]},
            {"name": "原型设计", "emoji": "🎨", "capabilities": ["ui_design"]},
            {"name": "前端开发", "emoji": "💻", "capabilities": ["code_generation"]},
            {"name": "后端开发", "emoji": "⚙️", "capabilities": ["code_generation"]},
            {"name": "测试", "emoji": "🧪", "capabilities": ["testing"]},
            {"name": "部署上线", "emoji": "🚀", "capabilities": ["deployment"]},
        ]
        self._action("init_pipeline", count=len(stages), stages=[
            {"name": s["name"], "emoji": s.get("emoji", "▶️")} for s in stages
        ]); time.sleep(0.3)
        self._emit("orchestrator", f"Decomposed into {len(stages)} stages", "success"); time.sleep(0.2)

        amap = {0: "general-agent", 1: "doc-writer-agent", 2: "code-gen-agent",
                3: "code-gen-agent", 4: "code-gen-agent", 5: "test-agent", 6: "general-agent"}
        for i, s in enumerate(stages):
            aid = amap.get(i, "general-agent")
            agent = self._registry.get(aid) if self._registry else None
            self._emit("orchestrator", f"Stage {i+1} '{s['name']}' → {agent.name if agent else aid}", "info"); time.sleep(0.06)

        self._emit("system", "Starting execution...", "success"); time.sleep(0.2)
        outputs = ["Requirements analyzed", "Technical spec created", "UI wireframes designed",
                   "React components built", "FastAPI endpoints created", "24 tests passed", "Docker configs generated"]
        for i, s in enumerate(stages):
            aid = amap.get(i, "general-agent")
            self._action("stage_update", index=i, status="running", agent=aid)
            self._emit(aid, f"Starting: {s['name']}", "thinking"); time.sleep(0.7)
            if self._mode == ExecutionMode.AGENT and i >= 2:
                self._emit("permission", f"Approval needed: write files for stage {i+1}", "warning"); time.sleep(0.2)
            self._emit(aid, outputs[min(i, len(outputs)-1)], "success")
            self._action("stage_update", index=i, status="completed"); time.sleep(0.1)

        self._emit("system", f"Done! {len(stages)}/{len(stages)} stages. Mode: {self._mode.value}", "success")


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    assets = get_assets_dir()
    html_path = assets / "index.html"
    if not html_path.exists(): raise FileNotFoundError(str(html_path))
    webview.create_window(
        title="OmniAgent Studio", html=html_path.read_text(encoding="utf-8"),
        js_api=OmniAgentAPI(), width=1280, height=860, min_size=(960, 600), resizable=True,
    )
    webview.start(debug=False, http_server=True)
