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
from ..core.llm_bridge import LLMBridge
from ..core.orchestrator import Orchestrator, OrchestratorConfig
from ..core.registry import AgentRegistry
from ..protocol import Task
from ..runtime.security import ExecutionMode, PermissionHandler
from ..runtime.executor import ToolExecutor
from ..tools.base import ToolRegistry
from ..tools.builtin.file_tools import ReadTool, WriteTool, EditTool, GlobTool, GrepTool
from ..tools.builtin.git_tools import GitStatusTool, GitDiffTool, GitLogTool, GitBranchTool
from ..tools.builtin.web_tools import WebFetchTool, WebSearchTool


# ── Built-in model definitions ──────────────────────────────────────────

BUILTIN_MODELS = [
    {
        "id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1", "context": "1M tokens",
        "pricing": "$0.44/$0.87 per 1M",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": True, "supports_streaming": True,
        "doc_url": "https://api-docs.deepseek.com/",
    },
    {
        "id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1", "context": "1M tokens",
        "pricing": "$0.14/$0.28 per 1M",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://api-docs.deepseek.com/",
    },
    {
        "id": "mimo-general-v2", "name": "MiMo General V2", "provider": "mimo",
        "base_url": "https://api.xiaomimimo.com/v1", "context": "128K tokens",
        "pricing": "Free tier available",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://platform.xiaomimimo.com/docs",
    },
    {
        "id": "claude-opus-4-7", "name": "Claude Opus 4.7", "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1", "context": "200K tokens",
        "pricing": "$15/$75 per 1M",
        "auth_format": "x-api-key", "api_format": "anthropic_messages",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": True, "supports_streaming": True,
        "doc_url": "https://docs.anthropic.com/en/api",
        "extra_headers": {"anthropic-version": "2023-06-01"},
    },
    {
        "id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6", "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1", "context": "200K tokens",
        "pricing": "$3/$15 per 1M",
        "auth_format": "x-api-key", "api_format": "anthropic_messages",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": True, "supports_streaming": True,
        "doc_url": "https://docs.anthropic.com/en/api",
        "extra_headers": {"anthropic-version": "2023-06-01"},
    },
    {
        "id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1", "context": "200K tokens",
        "pricing": "$1/$5 per 1M",
        "auth_format": "x-api-key", "api_format": "anthropic_messages",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://docs.anthropic.com/en/api",
        "extra_headers": {"anthropic-version": "2023-06-01"},
    },
    {
        "id": "gpt-4o", "name": "GPT-4o", "provider": "openai",
        "base_url": "https://api.openai.com/v1", "context": "128K tokens",
        "pricing": "$2.50/$10 per 1M",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://platform.openai.com/docs/api-reference",
    },
    {
        "id": "gpt-4.5", "name": "GPT-4.5", "provider": "openai",
        "base_url": "https://api.openai.com/v1", "context": "128K tokens",
        "pricing": "$75/$150 per 1M",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://platform.openai.com/docs/api-reference",
    },
    {
        "id": "qwen-max", "name": "通义千问 Max", "provider": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "context": "128K tokens",
        "pricing": "¥0.04/1K",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://help.aliyun.com/zh/model-studio/",
    },
    {
        "id": "qwen-plus", "name": "通义千问 Plus", "provider": "qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "context": "128K tokens",
        "pricing": "¥0.02/1K",
        "auth_format": "Bearer", "api_format": "openai_chat",
        "default_max_tokens": 4096, "default_temperature": 0.7,
        "supports_thinking": False, "supports_streaming": True,
        "doc_url": "https://help.aliyun.com/zh/model-studio/",
    },
]


class OmniAgentAPI:
    """JS ↔ Python bridge."""

    def __init__(self) -> None:
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._lock = threading.Lock()
        self._running = False
        self._events: queue.Queue = queue.Queue()
        self._mode: ExecutionMode = ExecutionMode.AGENT
        self._permissions = PermissionHandler(self._mode)
        self._tool_executor: ToolExecutor | None = None
        self._model_configs: dict[str, dict] = {}
        self._active_model_id: str = ""
        self._llm_bridge = LLMBridge()
        self._setup_registry()

    def _setup_registry(self) -> None:
        registry = AgentRegistry()
        for cls in [GeneralAgent, CodeGenAgent, CodeReviewAgent, DocWriterAgent, TestAgent]:
            temp = cls()
            registry.register(temp.descriptor, cls)
        self._registry = registry
        tool_reg = ToolRegistry()
        for t in [ReadTool(), WriteTool(), EditTool(), GlobTool(), GrepTool(),
                   GitStatusTool(), GitDiffTool(), GitLogTool(), GitBranchTool(),
                   WebFetchTool(), WebSearchTool()]:
            tool_reg.register(t)
        self._tool_registry = tool_reg
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
        return json.dumps({
            "models": [{
                "id": m["id"], "name": m["name"], "provider": m["provider"],
                "context": m["context"], "pricing": m["pricing"],
                "configured": m["id"] in self._model_configs,
                "active": m["id"] == self._active_model_id,
            } for m in BUILTIN_MODELS],
            "active_model": self._active_model_id,
        })

    def get_model_defaults(self, model_id: str) -> str:
        """Return detailed default config for a model based on official docs."""
        model = next((m for m in BUILTIN_MODELS if m["id"] == model_id), None)
        if not model:
            return json.dumps({"status": "error", "message": "Unknown model"})
        saved = self._model_configs.get(model_id, {})
        return json.dumps({
            "id": model["id"], "name": model["name"], "provider": model["provider"],
            "base_url": saved.get("base_url", model["base_url"]),
            "api_format": model["api_format"],
            "auth_format": model["auth_format"],
            "default_max_tokens": model["default_max_tokens"],
            "default_temperature": model["default_temperature"],
            "supports_thinking": model["supports_thinking"],
            "supports_streaming": model["supports_streaming"],
            "doc_url": model["doc_url"],
            "extra_headers": json.dumps(model.get("extra_headers", {})),
            "api_key": saved.get("api_key", ""),
            "max_tokens": saved.get("max_tokens", model["default_max_tokens"]),
            "temperature": saved.get("temperature", model["default_temperature"]),
            "base_url_override": saved.get("base_url", ""),
        })

    def save_model_config(self, model_id: str, config_json: str) -> str:
        """Save full model configuration from JSON."""
        try:
            cfg = json.loads(config_json)
            api_key = cfg.get("api_key", "")
            if not api_key:
                return json.dumps({"status": "error", "message": "API Key is required"})
            self._model_configs[model_id] = {
                "api_key": api_key,
                "base_url": cfg.get("base_url", ""),
                "max_tokens": cfg.get("max_tokens", 4096),
                "temperature": cfg.get("temperature", 0.7),
            }
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def select_model(self, model_id: str) -> str:
        cfg = self._model_configs.get(model_id)
        if not cfg or not cfg.get("api_key"):
            return json.dumps({"status": "error", "message": "请先配置 API Key"})
        self._active_model_id = model_id
        self._llm_bridge.configure(model_id, cfg["api_key"], cfg.get("base_url", ""))
        # Wire LLM provider into orchestrator's analyzer
        provider = self._llm_bridge.get_provider()
        if provider and self._orchestrator:
            from ..core.analyzer import TaskAnalyzer
            self._orchestrator.analyzer = TaskAnalyzer(llm_provider=provider)
        return json.dumps({"status": "ok", "active_model": model_id})

    def test_model_connection(self, model_id: str) -> str:
        cfg = self._model_configs.get(model_id)
        api_key = cfg.get("api_key") if cfg else ""
        model = next((m for m in BUILTIN_MODELS if m["id"] == model_id), None)
        if not model:
            return json.dumps({"status": "error", "message": "Unknown model"})
        if not api_key:
            return json.dumps({"status": "error", "message": "请先保存 API Key"})

        base_url = cfg.get("base_url", model["base_url"]).rstrip("/")
        is_anthropic = model["api_format"] == "anthropic_messages"

        try:
            import httpx
            headers = {"Content-Type": "application/json", "User-Agent": "OmniAgent/0.2"}
            if is_anthropic:
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
                body = {"model": model_id, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
                test_url = f"{base_url}/messages"
            else:
                headers["Authorization"] = f"Bearer {api_key}"
                body = {"model": model_id, "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
                test_url = f"{base_url}/chat/completions"

            with httpx.Client(timeout=20) as client:
                start = time.time()
                resp = client.post(test_url, json=body, headers=headers)
                elapsed_ms = round((time.time() - start) * 1000)

            if resp.status_code in (200, 201):
                data = resp.json()
                content = ""
                if is_anthropic:
                    blocks = data.get("content", [])
                    content = blocks[0].get("text", "") if blocks else ""
                else:
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return json.dumps({
                    "status": "ok",
                    "message": f"连接成功 — 响应: {content[:80]}",
                    "latency_ms": elapsed_ms,
                })
            else:
                err_text = resp.text[:300]
                try:
                    err_json = resp.json()
                    err_text = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    pass
                return json.dumps({"status": "error", "message": f"HTTP {resp.status_code}: {err_text}"})
        except Exception as e:
            return json.dumps({"status": "error", "message": f"网络错误: {str(e)[:150]}"})

    def get_model_usage(self, model_id: str) -> str:
        cfg = self._model_configs.get(model_id)
        if not cfg:
            return json.dumps({"status": "error", "message": "未配置"})
        usage = self._llm_bridge.get_usage(model_id) if self._llm_bridge else {}
        return json.dumps({
            "status": "ok", "model": model_id,
            "usage": {
                "total_requests": usage.get("requests", 0),
                "total_input_tokens": usage.get("input_tokens", 0),
                "total_output_tokens": usage.get("output_tokens", 0),
                "estimated_cost": usage.get("cost", "$0.00"),
            }
        })

    def get_llm_status(self) -> str:
        return json.dumps({
            "configured": self._llm_bridge.is_configured(),
            "active_model": self._active_model_id,
            "providers": self._llm_bridge.list_configured(),
        })

    # ── Real LLM Execution ──────────────────────────────────────────────

    def execute_task(self, task_text: str) -> str:
        """Execute a task using real LLM if configured, fallback to demo."""
        with self._lock:
            if self._running:
                return json.dumps({"status": "error", "message": "Already running"})
            self._running = True
            self._events = queue.Queue()

        provider = self._llm_bridge.get_provider()
        if provider and self._active_model_id:
            threading.Thread(target=self._real_llm_thread, args=(task_text, provider), daemon=True).start()
            return json.dumps({"status": "started", "mode": "llm"})
        else:
            threading.Thread(target=self._demo_thread, daemon=True).start()
            return json.dumps({"status": "started", "mode": "demo"})

    def _real_llm_thread(self, task_text: str, provider) -> None:
        """Real LLM-powered task execution."""
        try:
            self._emit("system", f"🤖 使用 {self._active_model_id} 进行任务分析…", "system")
            time.sleep(0.3)

            # Step 1: LLM Analysis
            self._emit("orchestrator", "正在分析任务…", "thinking")
            analysis_prompt = f"""Analyze this task and return JSON:
{{
  "domain": "software|video|document|data|general",
  "summary": "one sentence",
  "tech_stack": ["techs"],
  "stages": [{{"name":"Stage","description":"what to do","capabilities":["code_generation"]}}]
}}
Task: {task_text}"""

            try:
                completion = provider.complete_sync(
                    model=self._active_model_id,
                    messages=[{"role": "user", "content": analysis_prompt}],
                    max_tokens=800, temperature=0.3,
                )
                content = completion.get("content", "") if isinstance(completion, dict) else str(completion)
                # Try to extract JSON
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    analysis = json.loads(content[json_start:json_end])
                else:
                    analysis = {"domain": "general", "summary": task_text[:80],
                                "stages": [{"name": "执行任务", "description": task_text, "capabilities": ["general_purpose"]}]}
            except Exception as e:
                self._emit("orchestrator", f"LLM 分析失败: {e}，使用规则分析", "warning")
                analysis = {"domain": "general", "summary": task_text[:80],
                            "stages": [{"name": "执行任务", "description": task_text, "capabilities": ["general_purpose"]}]}

            domain = analysis.get("domain", "general")
            stages = analysis.get("stages", [{"name": "执行", "description": task_text, "capabilities": ["general_purpose"]}])
            self._emit("orchestrator", f"领域: {domain} | 分解为 {len(stages)} 个阶段", "success")
            self._action("init_pipeline", count=len(stages), stages=[
                {"name": s["name"], "emoji": "▶️"} for s in stages
            ])
            time.sleep(0.3)

            # Step 2: Execute stages with LLM
            for i, stage in enumerate(stages):
                stage_name = stage.get("name", f"Stage {i+1}")
                self._action("stage_update", index=i, status="running", agent="llm-agent")
                self._emit("llm-agent", f"执行: {stage_name}", "thinking")

                try:
                    stage_prompt = f"""You are executing stage '{stage_name}' of a larger task.
Task: {task_text}
Stage description: {stage.get('description', '')}
Previous context: {analysis.get('summary', '')}

Complete this stage. Be specific and actionable. Output the result directly (no JSON wrapper needed).
Response language: Chinese if the task is in Chinese, otherwise English."""
                    result = provider.complete_sync(
                        model=self._active_model_id,
                        messages=[{"role": "user", "content": stage_prompt}],
                        max_tokens=600, temperature=0.5,
                    )
                    content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                    self._emit("llm-agent", content[:200], "success")
                except Exception as e:
                    self._emit("llm-agent", f"阶段执行失败: {e}", "error")

                self._action("stage_update", index=i, status="completed")
                time.sleep(0.2)

            self._emit("system", f"✅ 任务完成 — 共 {len(stages)} 个阶段，模型: {self._active_model_id}", "success")
        except Exception as e:
            self._emit("system", f"执行错误: {e}", "error")
        finally:
            with self._lock:
                self._running = False
            self._action("demo_complete")

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

    def get_agents(self) -> str:
        if not self._registry: return "[]"
        return json.dumps([{
            "id": d.id, "name": d.name,
            "capabilities": [c.value for c in d.capabilities],
            "role": d.role.value, "provider": d.provider,
        } for d in self._registry.list_all()])

    def get_tools(self) -> str:
        if not hasattr(self, '_tool_registry'): return "[]"
        return json.dumps([{
            "name": t.name, "description": t.description,
            "category": t.category, "requires_approval": t.requires_approval,
        } for t in self._tool_registry.list_descriptors()])

    def get_audit_log(self) -> str:
        if self._tool_executor:
            return json.dumps([{
                "tool": r.tool_name, "agent": r.agent_id,
                "args": {k: str(v)[:50] for k, v in r.args.items()},
                "result": r.result[:200], "error": r.is_error,
                "duration_ms": round(r.duration_ms, 1), "time": r.timestamp,
            } for r in self._tool_executor.get_audit_log()[-50:]])
        return "[]"

    def get_conversations(self) -> str:
        """Return conversation history list. Placeholder for future persistence."""
        return json.dumps([])

    def get_system_info(self) -> str:
        """Return system status information for the status bar."""
        return json.dumps({
            "running": self._running,
            "mode": self._mode.value,
            "active_model": self._active_model_id,
            "agents": len(self._registry.list_all()) if self._registry else 0,
            "tools": len(self._tool_registry.list_descriptors()) if hasattr(self, '_tool_registry') else 0,
        })

    def _emit(self, source, message, level="info"):
        self._events.put({"type": "event", "source": source, "message": message, "level": level})

    def _action(self, action, **kw):
        self._events.put({"type": "action", "action": action, **kw})

    def _emit_tool_call(self, tool_name: str, args: dict, result: str, is_error: bool = False):
        self._events.put({
            "type": "tool_call", "tool": tool_name,
            "args": args, "result": str(result)[:500], "error": is_error,
        })

    def _demo_thread(self):
        try: self._run_demo()
        except Exception as e: self._emit("system", f"Error: {e}", "error")
        finally:
            with self._lock:
                self._running = False
            self._action("demo_complete")

    def _run_demo(self):
        self._emit("system", "⚠️ 未配置 LLM，使用 Demo 模式", "warning")
        time.sleep(0.3)
        for desc in (self._registry or AgentRegistry()).list_all():
            self._emit("system", f"Registered: {desc.name}", "info"); time.sleep(0.04)
        self._emit("system", "Demo orchestrator ready.", "success"); time.sleep(0.2)

        stages = [{"name": "需求确认", "emoji": "📋"}, {"name": "需求分析", "emoji": "🔬"},
                   {"name": "原型设计", "emoji": "🎨"}, {"name": "前端开发", "emoji": "💻"},
                   {"name": "后端开发", "emoji": "⚙️"}, {"name": "测试", "emoji": "🧪"},
                   {"name": "部署上线", "emoji": "🚀"}]
        self._action("init_pipeline", count=7, stages=stages); time.sleep(0.2)
        self._emit("orchestrator", "Decomposed into 7 stages (demo)", "info")

        amap = {0: "general-agent", 1: "doc-writer-agent", 2: "code-gen-agent",
                3: "code-gen-agent", 4: "code-gen-agent", 5: "test-agent", 6: "general-agent"}
        for i, s in enumerate(stages):
            aid = amap.get(i, "general-agent")
            self._action("stage_update", index=i, status="running", agent=aid)
            self._emit(aid, f"Starting: {s['name']}", "thinking"); time.sleep(0.6)
            self._emit(aid, f"Completed stage: {s['name']} (demo)", "success")
            self._action("stage_update", index=i, status="completed"); time.sleep(0.1)
        self._emit("system", "Demo complete. 配置 LLM 以启用真实调用。", "success")


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    assets = get_assets_dir()
    html_path = assets / "index.html"
    if not html_path.exists(): raise FileNotFoundError(str(html_path))
    api = OmniAgentAPI()
    webview.create_window(
        title="OmniAgent Studio",
        url=str(html_path),
        js_api=api,
        width=1280, height=860,
        min_size=(960, 600),
        resizable=True,
    )
    webview.start(debug=False, http_server=True)
