"""
OmniAgent Studio — Windows Desktop Application.

GUI backend: connects pywebview frontend to the orchestrator, LLM bridge,
agent registry, and tool executor.
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
from ..protocol import AgentCapability
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


_CONFIG_DIR = Path.home() / ".omniagent"
_CONFIG_PATH = _CONFIG_DIR / "gui_config.json"


class OmniAgentAPI:
    """JS <-> Python bridge for pywebview."""

    def __init__(self) -> None:
        self._registry: AgentRegistry | None = None
        self._orchestrator: Orchestrator | None = None
        self._lock = threading.Lock()
        self._running = False
        self._stop_flag = False
        self._events: queue.Queue = queue.Queue()
        self._mode: ExecutionMode = ExecutionMode.AGENT
        self._permissions = PermissionHandler(self._mode)
        self._tool_executor: ToolExecutor | None = None
        self._model_configs: dict[str, dict] = {}
        self._active_model_id: str = ""
        self._llm_bridge = LLMBridge()
        self._pending_approvals: list[dict] = []
        self._conversation_history: list[dict] = []
        self._load_persisted_config()
        self._setup_registry()
        self._auto_activate_model()

    # ── Config Persistence ──────────────────────────────────────────────

    def _load_persisted_config(self) -> None:
        """Load saved model configs from disk."""
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                self._model_configs = data.get("model_configs", {})
                self._active_model_id = data.get("active_model", "")
            except Exception:
                pass

    def _save_persisted_config(self) -> None:
        """Save current model configs to disk."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "model_configs": self._model_configs,
            "active_model": self._active_model_id,
        }
        _CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _auto_activate_model(self) -> None:
        """Auto-activate the previously selected model if config is available."""
        if self._active_model_id:
            cfg = self._model_configs.get(self._active_model_id)
            if cfg and cfg.get("api_key"):
                self._llm_bridge.configure(self._active_model_id, cfg["api_key"], cfg.get("base_url", ""))
                provider = self._llm_bridge.get_provider()
                if provider and self._orchestrator:
                    self._orchestrator.analyzer = TaskAnalyzer(llm_provider=provider)

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
        self._orchestrator = Orchestrator(registry, config=config, llm_bridge=self._llm_bridge)
        # Skill registry
        from ..skills.registry import SkillRegistry
        from ..skills.scanner import SkillScanner
        self._skill_registry = SkillRegistry()
        self._skill_registry.set_scanner(SkillScanner())
        self._skill_registry.discover()
        self._orchestrator.skill_registry = self._skill_registry
        # Enterprise modules
        from ..enterprise.rbac import RBACManager
        from ..enterprise.audit import AuditStore
        from ..enterprise.marketplace import PrivateMarketplace
        from ..enterprise.auth import AuthManager
        self._rbac = RBACManager()
        self._audit_store = AuditStore()
        self._marketplace = PrivateMarketplace()
        self._auth = AuthManager(self._rbac)

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
            self._save_persisted_config()
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
            self._orchestrator.analyzer = TaskAnalyzer(llm_provider=provider)
        self._save_persisted_config()
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

    # ── Task Execution ──────────────────────────────────────────────────

    def execute_task(self, task_text: str) -> str:
        """Execute a task using real LLM if configured, fallback to demo."""
        # Handle special commands
        if task_text.strip().startswith("/"):
            return self._handle_command(task_text.strip())

        with self._lock:
            if self._running:
                return json.dumps({"status": "error", "message": "Already running"})
            self._running = True
            self._stop_flag = False
            self._events = queue.Queue()

        # Store conversation entry
        self._conversation_history.append({"role": "user", "content": task_text})

        provider = self._llm_bridge.get_provider()
        if provider and self._active_model_id:
            threading.Thread(target=self._real_llm_thread, args=(task_text,), daemon=True).start()
            return json.dumps({"status": "started", "mode": "llm"})
        else:
            threading.Thread(target=self._demo_thread, args=(task_text,), daemon=True).start()
            return json.dumps({"status": "started", "mode": "demo"})

    def stop_task(self) -> str:
        """Signal the running task to stop."""
        if not self._running:
            return json.dumps({"status": "error", "message": "No task running"})
        self._stop_flag = True
        return json.dumps({"status": "ok"})

    def _handle_command(self, cmd: str) -> str:
        """Handle slash commands from chat input."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        responses = {
            "/help": "可用命令:\n  /help — 显示帮助\n  /status — 系统状态\n  /clear — 清空对话\n  /models — 已配置模型\n  /agents — 已注册 Agent\n  /tools — 已注册工具\n  /workflows — 可用工作流模板\n  /skills — 已安装技能",
            "/clear": "__CLEAR__",
        }
        if command in responses:
            resp = responses[command]
            if resp == "__CLEAR__":
                return json.dumps({"status": "started", "mode": "command", "action": "clear"})
            self._emit("system", resp, "info")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/status":
            info = self.get_system_info()
            self._emit("system", f"系统状态:\n```json\n{info}\n```", "info")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/models":
            models = [m for m in BUILTIN_MODELS if m["id"] in self._model_configs]
            if models:
                lines = [f"  {m['id']} — {m['name']}" for m in models]
                self._emit("system", f"已配置模型:\n" + "\n".join(lines), "info")
            else:
                self._emit("system", "未配置任何模型。请在设置中配置 API Key。", "warning")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/agents":
            agents = self._registry.list_all() if self._registry else []
            lines = [f"  {d.id} — {d.name} [{', '.join(c.value for c in d.capabilities[:3])}]" for d in agents]
            self._emit("system", f"已注册 Agent ({len(agents)}):\n" + "\n".join(lines), "info")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/tools":
            tools = self._tool_registry.list_descriptors() if hasattr(self, '_tool_registry') else []
            lines = [f"  {t.name} — {t.description[:50]}" for t in tools]
            self._emit("system", f"已注册工具 ({len(tools)}):\n" + "\n".join(lines), "info")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/workflows":
            workflows = self._orchestrator.list_workflows() if self._orchestrator else []
            if workflows:
                lines = []
                for wf in workflows:
                    stage_names = " → ".join(s["name"] for s in wf["stages"])
                    lines.append(f"  {wf['name']} — {wf['description']}\n    {stage_names}")
                self._emit("system", f"可用工作流 ({len(workflows)}):\n" + "\n".join(lines), "info")
            else:
                self._emit("system", "无可用工作流模板。", "warning")
            return json.dumps({"status": "started", "mode": "command"})
        elif command == "/skills":
            skills = self._skill_registry.to_list() if hasattr(self, '_skill_registry') else []
            if skills:
                lines = []
                for s in skills:
                    status = "✅" if s["enabled"] else "❌"
                    caps = ", ".join(s["capabilities"][:3]) if s["capabilities"] else "none"
                    lines.append(f"  {status} {s['id']} v{s['version']} — {s['name']} [{caps}]")
                self._emit("system", f"已安装技能 ({len(skills)}):\n" + "\n".join(lines), "info")
            else:
                self._emit("system", "未安装任何技能。使用 install_skill() 安装。", "warning")
            return json.dumps({"status": "started", "mode": "command"})
        else:
            self._emit("system", f"未知命令: {command}。输入 /help 查看可用命令。", "warning")
            return json.dumps({"status": "started", "mode": "command"})

    # ── Real LLM Execution (via LLMBridge) ──────────────────────────────

    def _real_llm_thread(self, task_text: str) -> None:
        """Real LLM-powered task execution using LLMBridge.complete_sync()."""
        try:
            model_name = self._active_model_id
            self._emit("system", f"使用 {model_name} 分析任务…", "system")
            time.sleep(0.2)

            # Phase 1: Task Analysis via LLM
            self._emit("orchestrator", "正在分析任务需求…", "thinking")
            analysis_prompt = f"""分析以下任务，返回JSON格式:
{{
  "domain": "software|video|document|data|general",
  "summary": "一句话概述",
  "tech_stack": ["技术栈"],
  "complexity": "low|medium|high",
  "stages": [
    {{"name": "阶段名称", "description": "具体做什么", "capabilities": ["code_generation"]}}
  ]
}}
任务: {task_text}"""

            result = self._llm_bridge.complete_sync(
                model=model_name,
                messages=[{"role": "user", "content": analysis_prompt}],
                max_tokens=800, temperature=0.3,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)

            if result.get("error"):
                self._emit("orchestrator", f"LLM 调用失败: {result['error']}，使用规则分析", "warning")
                analysis = self._rule_based_analysis(task_text)
            else:
                analysis = self._parse_analysis(content, task_text)

            domain = analysis.get("domain", "general")
            stages = analysis.get("stages", [])
            complexity = analysis.get("complexity", "medium")
            summary = analysis.get("summary", task_text[:80])

            self._emit("orchestrator", f"领域: {domain} | 复杂度: {complexity} | {len(stages)} 个阶段", "success")
            self._emit("orchestrator", f"任务概述: {summary}", "info")

            if not stages:
                stages = [{"name": "执行任务", "description": task_text, "capabilities": ["general_purpose"]}]

            # Init pipeline visualization
            self._action("init_pipeline", count=len(stages), stages=[
                {"name": s["name"], "emoji": self._stage_emoji(s)} for s in stages
            ])
            time.sleep(0.2)

            # Phase 2: Execute each stage
            context_accumulator = []
            for i, stage in enumerate(stages):
                if self._stop_flag:
                    self._emit("system", "任务已取消", "warning")
                    break

                stage_name = stage.get("name", f"Stage {i+1}")
                stage_desc = stage.get("description", "")
                caps = stage.get("capabilities", ["general_purpose"])

                # Find best agent for this stage
                agent_id, agent_name, score, breakdown = self._find_agent_for_stage(caps, task_text)
                self._action("stage_update", index=i, status="running", agent=agent_id)
                self._emit(agent_id, f"开始: {stage_name} (综合评分: {score:.0%})", "thinking")
                if breakdown:
                    self._emit("orchestrator", f"评分详情: {breakdown}", "info")

                # Build context from previous stages
                context_str = ""
                if context_accumulator:
                    context_str = "\n前序阶段结果:\n" + "\n".join(
                        f"- {c['stage']}: {c['summary']}" for c in context_accumulator[-3:]
                    )

                # Agent mode: emit approval request
                if self._mode == ExecutionMode.AGENT:
                    approval = {
                        "id": str(uuid.uuid4()),
                        "stage": i,
                        "agent": agent_name,
                        "action": f"执行阶段: {stage_name}",
                        "description": stage_desc,
                    }
                    self._pending_approvals.append(approval)
                    self._emit("approval_request", json.dumps(approval), "warning")
                    # Wait for approval (poll every 100ms, timeout 60s)
                    waited = 0
                    while approval in self._pending_approvals and waited < 600 and not self._stop_flag:
                        time.sleep(0.1)
                        waited += 1
                    if approval not in self._pending_approvals:
                        # Check if denied
                        if approval.get("denied"):
                            self._emit(agent_id, f"阶段 {stage_name} 被拒绝", "warning")
                            self._action("stage_update", index=i, status="failed")
                            continue
                    elif self._stop_flag:
                        break

                # Execute stage via LLM
                stage_prompt = f"""你正在执行多阶段任务的第 {i+1}/{len(stages)} 阶段。
任务: {task_text}
当前阶段: {stage_name}
阶段描述: {stage_desc}
{context_str}

请直接完成这个阶段的工作，输出具体、可执行的结果。
语言: 如果任务是中文则用中文，否则用英文。"""

                stage_result = self._llm_bridge.complete_sync(
                    model=model_name,
                    messages=[{"role": "user", "content": stage_prompt}],
                    max_tokens=1200, temperature=0.5,
                )
                stage_content = stage_result.get("content", "") if isinstance(stage_result, dict) else str(stage_result)

                if stage_result.get("error"):
                    self._emit(agent_id, f"阶段执行失败: {stage_result['error']}", "error")
                    self._action("stage_update", index=i, status="failed")
                    self._orchestrator.scorer.record_failure(agent_id)
                else:
                    # Show result (truncated for display)
                    display_text = stage_content[:500] + ("…" if len(stage_content) > 500 else "")
                    self._emit(agent_id, display_text, "success")
                    self._action("stage_update", index=i, status="completed")
                    self._orchestrator.scorer.record_success(agent_id)

                    # LLM-based context summarization for next stages
                    summary = self._orchestrator.summarize_output(stage_name, agent_name, stage_content)
                    context_accumulator.append({
                        "stage": stage_name,
                        "agent": agent_name,
                        "summary": summary,
                    })

                time.sleep(0.15)

            if not self._stop_flag:
                self._emit("system", f"任务完成 — {len(stages)} 个阶段, 模型: {model_name}", "success")
                self._conversation_history.append({"role": "assistant", "content": f"完成 {len(stages)} 个阶段"})

        except Exception as e:
            self._emit("system", f"执行错误: {e}", "error")
        finally:
            with self._lock:
                self._running = False
                self._stop_flag = False
            self._action("task_complete")

    def _rule_based_analysis(self, task_text: str) -> dict:
        """Fallback rule-based analysis when LLM is unavailable."""
        text_lower = task_text.lower()
        if any(k in text_lower for k in ["代码", "编程", "开发", "code", "build", "api"]):
            domain = "software"
            stages = [
                {"name": "需求分析", "description": "分析功能需求", "capabilities": ["general_purpose"]},
                {"name": "架构设计", "description": "设计系统架构", "capabilities": ["architecture_design"]},
                {"name": "代码实现", "description": "编写核心代码", "capabilities": ["code_generation"]},
                {"name": "代码审查", "description": "审查代码质量", "capabilities": ["code_review"]},
                {"name": "测试", "description": "编写和运行测试", "capabilities": ["testing"]},
            ]
        elif any(k in text_lower for k in ["文档", "文章", "写作", "document", "write"]):
            domain = "document"
            stages = [
                {"name": "内容规划", "description": "规划文档结构", "capabilities": ["general_purpose"]},
                {"name": "撰写初稿", "description": "撰写文档内容", "capabilities": ["documentation"]},
                {"name": "审校修订", "description": "审校和修订", "capabilities": ["code_review"]},
            ]
        else:
            domain = "general"
            stages = [
                {"name": "理解需求", "description": "分析任务需求", "capabilities": ["general_purpose"]},
                {"name": "执行任务", "description": task_text, "capabilities": ["general_purpose"]},
                {"name": "输出结果", "description": "整理输出结果", "capabilities": ["documentation"]},
            ]
        return {"domain": domain, "summary": task_text[:80], "stages": stages, "complexity": "medium"}

    def _parse_analysis(self, content: str, task_text: str) -> dict:
        """Parse LLM analysis response, extracting JSON."""
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(content[json_start:json_end])
        except json.JSONDecodeError:
            pass
        return self._rule_based_analysis(task_text)

    def _find_agent_for_stage(self, capabilities: list[str], task_desc: str = "") -> tuple[str, str, float, str]:
        """Find the best matching agent using composite scorer. Returns (id, name, score, breakdown_str)."""
        if not self._registry:
            return "general-agent", "GeneralAgent", 0.5, ""
        caps = []
        for c in capabilities:
            try:
                caps.append(AgentCapability(c))
            except ValueError:
                pass
        if not caps:
            caps = [AgentCapability.GENERAL_PURPOSE]
        candidates = self._registry.find_by_capability(caps)
        if not candidates:
            return "general-agent", "GeneralAgent", 0.5, ""

        agent_descs = [desc for desc, _ in candidates]
        use_llm = bool(self._llm_bridge.is_configured())
        breakdowns = self._orchestrator.scorer.rank_agents(
            task_desc, agent_descs, caps, use_llm=use_llm,
        )
        if breakdowns:
            best = breakdowns[0]
            breakdown_str = (
                f"cap:{best.capability_score:.0%} llm:{best.llm_score:.0%} "
                f"rep:{best.reputation_score:.0%}"
            )
            if best.llm_reasoning:
                breakdown_str += f" — {best.llm_reasoning}"
            return best.agent_id, best.agent_name, best.composite_score, breakdown_str
        return "general-agent", "GeneralAgent", 0.5, ""

    def _stage_emoji(self, stage: dict) -> str:
        """Pick an emoji for a stage based on its capabilities."""
        caps = stage.get("capabilities", [])
        emoji_map = {
            "code_generation": "💻", "code_review": "🔍", "architecture_design": "🏗️",
            "testing": "🧪", "deployment": "🚀", "documentation": "📝",
            "ui_design": "🎨", "data_analysis": "📊", "general_purpose": "▶️",
        }
        for c in caps:
            if c in emoji_map:
                return emoji_map[c]
        return "▶️"

    # ── Demo Mode ───────────────────────────────────────────────────────

    def _demo_thread(self, task_text: str) -> None:
        try:
            self._run_demo(task_text)
        except Exception as e:
            self._emit("system", f"Error: {e}", "error")
        finally:
            with self._lock:
                self._running = False
                self._stop_flag = False
            self._action("task_complete")

    def _run_demo(self, task_text: str) -> None:
        """Demo mode: shows analysis + simulated stages, using actual user input."""
        self._emit("system", "未配置 LLM，使用演示模式", "warning")
        time.sleep(0.2)

        # Show registered agents
        agents = self._registry.list_all() if self._registry else []
        self._emit("system", f"已注册 {len(agents)} 个 Agent，{len(self._tool_registry.list_descriptors())} 个工具", "info")
        time.sleep(0.1)

        # Rule-based analysis (same as LLM fallback)
        analysis = self._rule_based_analysis(task_text)
        domain = analysis["domain"]
        stages = analysis["stages"]

        self._emit("orchestrator", f"任务分析 — 领域: {domain}, 分解为 {len(stages)} 个阶段", "success")
        self._emit("orchestrator", f"概述: {analysis['summary']}", "info")
        time.sleep(0.2)

        # Init pipeline
        self._action("init_pipeline", count=len(stages), stages=[
            {"name": s["name"], "emoji": self._stage_emoji(s)} for s in stages
        ])
        time.sleep(0.15)

        # Execute stages
        for i, stage in enumerate(stages):
            if self._stop_flag:
                self._emit("system", "任务已取消", "warning")
                break

            stage_name = stage["name"]
            caps = stage.get("capabilities", ["general_purpose"])
            agent_id, agent_name, score, breakdown = self._find_agent_for_stage(caps, task_text)

            self._action("stage_update", index=i, status="running", agent=agent_id)
            self._emit(agent_id, f"开始: {stage_name} (综合评分: {score:.0%})", "thinking")
            if breakdown:
                self._emit("orchestrator", f"评分详情: {breakdown}", "info")
            time.sleep(0.5)

            self._emit(agent_id, f"完成阶段: {stage_name}（演示模式，配置 LLM 以获取真实结果）", "success")
            self._action("stage_update", index=i, status="completed")
            time.sleep(0.1)

        if not self._stop_flag:
            self._emit("system", f"演示完成 — {len(stages)} 个阶段。配置 LLM 启用真实执行。", "success")

    # ── Approvals ───────────────────────────────────────────────────────

    def get_pending_approvals(self) -> str:
        return json.dumps(self._pending_approvals)

    def approve_tool(self, approval_id: str) -> str:
        for a in self._pending_approvals:
            if a["id"] == approval_id:
                self._pending_approvals.remove(a)
                return json.dumps({"status": "ok"})
        return json.dumps({"status": "error", "message": "Not found"})

    def deny_tool(self, approval_id: str) -> str:
        for a in self._pending_approvals:
            if a["id"] == approval_id:
                a["denied"] = True
                self._pending_approvals.remove(a)
                return json.dumps({"status": "ok"})
        return json.dumps({"status": "error", "message": "Not found"})

    # ── Events ──────────────────────────────────────────────────────────

    def poll_events(self) -> str:
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return json.dumps(events)

    def _emit(self, source, message, level="info"):
        self._events.put({"type": "event", "source": source, "message": message, "level": level})

    def _action(self, action, **kw):
        self._events.put({"type": "action", "action": action, **kw})

    def _emit_tool_call(self, tool_name: str, args: dict, result: str, is_error: bool = False):
        self._events.put({
            "type": "tool_call", "tool": tool_name,
            "args": args, "result": str(result)[:500], "error": is_error,
        })

    # ── Status ──────────────────────────────────────────────────────────

    def get_status(self) -> str:
        return json.dumps({"running": self._running, "mode": self._mode.value,
                           "agents": len(self._registry.list_all()) if self._registry else 0})

    def get_agents(self) -> str:
        if not self._registry:
            return "[]"
        return json.dumps([{
            "id": d.id, "name": d.name,
            "capabilities": [c.value for c in d.capabilities],
            "role": d.role.value, "provider": d.provider,
        } for d in self._registry.list_all()])

    def get_tools(self) -> str:
        if not hasattr(self, '_tool_registry'):
            return "[]"
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
        return json.dumps(self._conversation_history[-50:])

    def get_system_info(self) -> str:
        return json.dumps({
            "running": self._running,
            "mode": self._mode.value,
            "active_model": self._active_model_id,
            "agents": len(self._registry.list_all()) if self._registry else 0,
            "tools": len(self._tool_registry.list_descriptors()) if hasattr(self, '_tool_registry') else 0,
        })

    # ── Workflows ───────────────────────────────────────────────────────

    def list_workflows(self) -> str:
        """Return all available workflow templates."""
        if not self._orchestrator:
            return "[]"
        return json.dumps(self._orchestrator.list_workflows())

    def register_workflow(self, config_json: str) -> str:
        """Register a custom workflow from JSON config."""
        try:
            cfg = json.loads(config_json)
            name = cfg.get("name", "")
            description = cfg.get("description", "")
            stages = cfg.get("stages", [])
            if not name or not stages:
                return json.dumps({"status": "error", "message": "name and stages required"})
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                self._orchestrator.register_custom_workflow(name, description, stages)
            )
            loop.close()
            return json.dumps({"status": "ok", "name": name, "stages": len(stages)})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # ── Skills ───────────────────────────────────────────────────────────

    def get_skills(self) -> str:
        """Return all registered skills as JSON."""
        if not hasattr(self, '_skill_registry'):
            return "[]"
        return json.dumps(self._skill_registry.to_list())

    def install_skill(self, git_url: str) -> str:
        """Install a skill from a git URL."""
        try:
            from ..skills.installer import install_skill_from_git
            manifest = install_skill_from_git(git_url)
            from ..skills.models import InstalledSkill
            from ..skills.installer import SKILLS_DIR
            skill_path = SKILLS_DIR / manifest.id
            self._skill_registry.register(InstalledSkill(
                manifest=manifest, path=skill_path,
            ))
            return json.dumps({
                "status": "ok",
                "id": manifest.id,
                "name": manifest.name,
                "version": manifest.version,
            })
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def uninstall_skill(self, skill_id: str) -> str:
        """Uninstall a skill."""
        try:
            from ..skills.installer import uninstall_skill
            if uninstall_skill(skill_id):
                self._skill_registry.unregister(skill_id)
                return json.dumps({"status": "ok"})
            return json.dumps({"status": "error", "message": "Skill not found"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def toggle_skill(self, skill_id: str, enabled: bool) -> str:
        """Enable or disable a skill."""
        if enabled:
            ok = self._skill_registry.enable(skill_id)
        else:
            ok = self._skill_registry.disable(skill_id)
        if ok:
            return json.dumps({"status": "ok"})
        return json.dumps({"status": "error", "message": "Skill not found"})

    def search_community_skills(self, query: str) -> str:
        """Search the community skill index."""
        try:
            from ..skills.community import SkillCommunityRegistry
            reg = SkillCommunityRegistry()
            results = reg.search(query)
            return json.dumps({"status": "ok", "results": results})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # ── Enterprise: RBAC ────────────────────────────────────────────────

    def get_users(self) -> str:
        """List all RBAC users."""
        try:
            users = self._rbac.list_users()
            return json.dumps([u.to_dict() for u in users])
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def create_user(self, username: str, display_name: str, email: str, role: str) -> str:
        """Create a new RBAC user."""
        try:
            from ..enterprise.rbac import Role
            user = self._rbac.create_user(
                username=username, display_name=display_name,
                email=email, role=Role(role),
            )
            return json.dumps({"status": "ok", "user": user.to_dict()})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def update_user_role(self, user_id: str, new_role: str) -> str:
        """Update a user's role."""
        try:
            from ..enterprise.rbac import Role
            ok = self._rbac.update_user(user_id, role=Role(new_role))
            return json.dumps({"status": "ok" if ok else "error"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def deactivate_user(self, user_id: str) -> str:
        """Deactivate a user."""
        try:
            ok = self._rbac.deactivate_user(user_id)
            return json.dumps({"status": "ok" if ok else "error"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # ── Enterprise: Audit ───────────────────────────────────────────────

    def query_audit(self, filters_json: str) -> str:
        """Query audit log with filters."""
        try:
            f = json.loads(filters_json) if filters_json else {}
            entries = self._audit_store.query(
                start_time=f.get("start_time"),
                end_time=f.get("end_time"),
                tool_name=f.get("tool_name"),
                user_id=f.get("user_id"),
                is_error=f.get("is_error"),
                limit=f.get("limit", 100),
                offset=f.get("offset", 0),
            )
            return json.dumps([e.to_dict() for e in entries])
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def get_audit_stats(self) -> str:
        """Return audit log aggregate statistics."""
        try:
            return json.dumps(self._audit_store.get_stats())
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def purge_audit(self, before_timestamp: float) -> str:
        """Purge audit entries older than timestamp."""
        try:
            deleted = self._audit_store.purge_before(before_timestamp)
            return json.dumps({"status": "ok", "deleted": deleted})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # ── Enterprise: Marketplace ─────────────────────────────────────────

    def search_marketplace(self, query: str = "", item_type: str = "") -> str:
        """Search the private marketplace catalog."""
        try:
            entries = self._marketplace.search(
                query=query, item_type=item_type or None, status=None,
            )
            return json.dumps([e.to_dict() for e in entries])
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def publish_to_marketplace(self, entry_json: str, published_by: str) -> str:
        """Publish an item to the private marketplace."""
        try:
            from ..enterprise.marketplace import CatalogEntry
            data = json.loads(entry_json)
            entry = CatalogEntry.from_dict(data)
            self._marketplace.publish(entry, published_by)
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def marketplace_submit_review(self, item_id: str, item_type: str, submitted_by: str) -> str:
        """Submit a marketplace item for review."""
        try:
            self._marketplace.submit_for_review(item_id, item_type, submitted_by)
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def marketplace_approve(self, item_id: str, item_type: str, approved_by: str) -> str:
        """Approve a marketplace item."""
        try:
            self._marketplace.approve(item_id, item_type, approved_by)
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def marketplace_reject(self, item_id: str, item_type: str, rejected_by: str, reason: str = "") -> str:
        """Reject a marketplace item."""
        try:
            self._marketplace.reject(item_id, item_type, rejected_by, reason)
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    # ── Enterprise: Auth ────────────────────────────────────────────────

    def get_auth_providers(self) -> str:
        """List configured auth providers."""
        return json.dumps(self._auth.list_providers())

    def auth_login(self, username: str, password: str, provider: str = "mock") -> str:
        """Login via auth provider."""
        try:
            token = self._auth.login(username, password, provider)
            if token:
                return json.dumps({"status": "ok", "token": token})
            return json.dumps({"status": "error", "message": "Authentication failed"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def auth_logout(self, token: str) -> str:
        """Logout and invalidate session."""
        self._auth.logout(token)
        return json.dumps({"status": "ok"})


def get_assets_dir() -> Path:
    return Path(__file__).parent / "assets"


def launch_gui() -> None:
    assets = get_assets_dir()
    html_path = assets / "index.html"
    if not html_path.exists():
        raise FileNotFoundError(str(html_path))
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
