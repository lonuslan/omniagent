# OmniAgent Studio

<div align="center">

**自主多Agent协同通用平台 | Autonomous Multi-Agent Collaborative Platform**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-41%20passed-success.svg)]()

*一个 Agent 做一件事，一百个 Agent 协作完成一个项目*

</div>

---

## 这是什么？

**OmniAgent Studio** 是一个全新的多 Agent 协同工作平台。核心理念：

> 当你提出一个需求时，系统自动分析任务、分解为子任务、选择最合适的 Agent 去执行每个部分，最终把结果聚合呈现给你。

它不是另一个 AI 编程助手。它是一个 **Agent 的导演** —— 你只需要提需求，它来指挥整个"剧组"。

### 为什么与众不同？

| | 传统 AI 工具 | OmniAgent Studio |
|---|---|---|
| 任务模式 | 单一 Agent 串行执行 | **多 Agent 并行协同** |
| 领域范围 | 专注编程 | **编程、视频、文档、数据……任意领域** |
| 工作流程 | 无固定流程 | **内置专业 Workflow（需求→设计→编码→测试→部署）** |
| Agent 选择 | 手动指定 | **自动分析 + 能力匹配评分** |
| 扩展性 | 插件/扩展 | **三源 Agent 生态（内置/自定义/Marketplace）** |
| 协作方式 | 无 | **消息总线 + Handoff 协议 + Request/Response** |
| 界面 | CLI/TUI | **Windows 桌面应用 + TUI** |

---

## 核心能力

### 自主任务编排

```
用户: "帮我开发一个电商网站"

Orchestrator 自动分析:
  ├─ 领域识别: software → 使用 software_lifecycle 工作流
  ├─ 任务分解:
  │   ├─ [需求确认] → GeneralAgent
  │   ├─ [需求分析] → DocWriterAgent
  │   ├─ [原型设计] → CodeGenAgent (UI focus)
  │   ├─ [前端开发] → CodeGenAgent (React/TypeScript)
  │   ├─ [后端开发] → CodeGenAgent (Python/FastAPI)
  │   ├─ [测试]     → TestAgent + CodeReviewAgent
  │   └─ [部署]     → GeneralAgent (deploy config)
  └─ 按依赖顺序并行/串行执行
```

### 跨领域通用

同一套编排引擎，适用于完全不同的领域：

| 领域 | Workflow 阶段 | 涉及能力 |
|------|--------------|----------|
| 软件开发 | 需求→分析→原型→前端→后端→测试→部署 | CodeGen, Review, Test, Doc |
| 视频制作 | 脚本→素材→剪辑→音频→转场→审阅→导出 | Video, Audio, Copywriting |
| 文档写作 | 大纲→初稿→审阅→定稿 | Documentation, Copywriting |
| 数据分析 | 采集→清洗→分析→可视化 | DataAnalysis |

### 三源 Agent 生态

```
builtin (内置)          custom (自定义)         marketplace (社区)
    │                       │                       │
    ├─ GeneralAgent         ├─ CLI 创建             ├─ GitHub Agent 仓库
    ├─ CodeGenAgent         ├─ UI Builder           ├─ Community Hub
    ├─ CodeReviewAgent      ├─ Python SDK           ├─ Enterprise Catalog
    ├─ DocWriterAgent       └─ 声明式配置            └─ 一行命令安装
    └─ TestAgent
```

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    OmniAgent Studio                       │
├─────────────────────────────────────────────────────────┤
│  GUI (pywebview) │ TUI (textual) │ CLI (typer)          │
├─────────────────────────────────────────────────────────┤
│  Orchestrator (任务分析 → 能力匹配 → Agent分配)           │
├─────────────────────────────────────────────────────────┤
│  Registry │ Workflow Engine │ Collaboration Bus          │
├─────────────────────────────────────────────────────────┤
│  Agent Runtime (沙箱隔离 │ LLM 连接池 │ 工具执行)         │
├─────────────────────────────────────────────────────────┤
│  Security (Plan/Agent/Auto 三种权限模式)                  │
├─────────────────────────────────────────────────────────┤
│  LLM Providers (MiMo │ DeepSeek │ Claude │ OpenAI)      │
└─────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| **Protocol** | `protocol.py` | 核心类型系统、Agent/Task/Message/Event 定义 |
| **Registry** | `core/registry.py` | Agent 注册、发现、能力匹配评分算法 |
| **Orchestrator** | `core/orchestrator.py` | 任务分析、分解、Agent 选择、执行协调 |
| **Workflow** | `core/workflow.py` | 多阶段工作流模板（软件/视频/文档） |
| **Collaboration** | `collaboration/bus.py` | Agent 间消息总线、Handoff 协议 |
| **Runtime** | `runtime/` | Agent 沙箱、LLM 连接池、工具执行器、事件流 |
| **Security** | `runtime/security.py` | Plan/Agent/Auto 三种执行模式 + 工作区策略 |
| **LLM** | `llm/` | 统一 Provider 层（MiMo/DeepSeek/Claude/OpenAI） |
| **Tools** | `tools/` | 声明式工具框架，兼容 Function Calling |
| **GUI** | `gui/` | Windows 桌面应用（pywebview + HTML/CSS） |
| **TUI** | `tui/` | 终端仪表盘（textual 框架） |

### 内置 Agent

| Agent | ID | 能力 |
|-------|-----|------|
| General Purpose Agent | `general-agent` | 通用任务处理、需求澄清 |
| Code Generation Agent | `code-gen-agent` | 前后端代码生成 (React, Python, Go...) |
| Code Review Agent | `code-review-agent` | 代码审查、安全审计、性能分析 |
| Documentation Writer | `doc-writer-agent` | 文档、报告、文案生成 |
| Test Agent | `test-agent` | 测试用例生成和执行 |

---

## 快速开始

### 环境要求

- Python 3.11+
- Windows 10+ (GUI 需要 WebView2)

### 安装

```bash
git clone https://github.com/your-org/omniagent.git
cd omniagent
pip install -e ".[dev]"
```

### 启动

```bash
# Windows 桌面应用（推荐）
omniagent gui

# 终端仪表盘
omniagent tui

# 命令行执行
omniagent run "Build a REST API for a blog platform"

# 查看所有 Agent
omniagent agent list
```

### 运行测试

```bash
pytest tests/ -v
# 41 tests passed
```

### 运行 Demo

```bash
python examples/demo_software_project.py   # 软件开发全流程
python examples/demo_video_production.py    # 视频制作全流程
```

---

## 项目结构

```
omniagent/
├── src/omniagent/
│   ├── protocol.py              # 核心类型和协议定义
│   ├── cli.py                   # CLI 入口
│   ├── core/
│   │   ├── registry.py          # Agent 注册中心 + 能力匹配
│   │   ├── orchestrator.py      # 任务编排器
│   │   └── workflow.py          # 工作流引擎
│   ├── runtime/
│   │   ├── sandbox.py           # Agent 沙箱环境
│   │   ├── pool.py              # LLM 连接池
│   │   ├── executor.py          # 工具执行引擎
│   │   ├── stream.py            # 事件流
│   │   └── security.py          # 权限系统
│   ├── agents/
│   │   ├── base.py              # Agent 基类
│   │   └── builtin/             # 内置 Agent
│   ├── llm/
│   │   ├── provider.py          # LLM Provider 抽象
│   │   ├── types.py             # 统一类型
│   │   └── providers/           # 各平台实现
│   ├── tools/
│   │   ├── base.py              # Tool 框架
│   │   └── builtin/             # 内置工具
│   ├── collaboration/
│   │   └── bus.py               # 协作消息总线
│   ├── gui/
│   │   ├── app.py               # GUI 应用
│   │   └── assets/              # 前端资源
│   └── tui/
│       ├── app.py               # TUI 应用
│       ├── demo.py              # TUI 演示
│       └── widgets/             # TUI 组件
├── examples/                    # 示例演示
├── tests/                       # 测试（41 个）
├── pyproject.toml               # 项目配置
└── LICENSE                      # MIT
```

---

## GUI 界面

```
┌──────────────────────────────────────────────────────────┐
│  🎯 OmniAgent Studio                       ⚙️  ─ □ ✕   │
├────┬──────────────────────────────────┬──────────────────┤
│ 📁 │  💬 对话区域                      │ 🤖 Agent 状态    │
│ 🔍 │                                  │                  │
│ ⟠  │  用户: Build a todo app…         │ ○ Orchestrator   │
│ 🧩 │  🎯 Orchestrator: 分析中…         │ ○ CodeGen Agent  │
│    │  ┌──────────────────────┐       │ ○ Review Agent   │
│    │  │ ✅ 需求确认 → General │       │ ○ Doc Writer     │
│    │  │ ✅ 需求分析 → Doc     │       │ ○ Test Agent     │
│    │  │ ⚡ 原型设计 → CodeGen │       │                  │
│    │  └──────────────────────┘       │                  │
├────┴──────────────────────────────────┴──────────────────┤
│  > 描述你的任务…                           🎤 📎 [↑]     │
├──────────────────────────────────────────────────────────┤
│  ● 就绪  │  Stage 3/7  │  v0.2.0  │  5 Agents           │
└──────────────────────────────────────────────────────────┘
```

- **左侧图标栏**：文件浏览、搜索、Git、插件市场（后续开放）
- **对话式主区域**：任务以聊天消息呈现，Pipeline 以卡片嵌入
- **右侧 Agent 面板**：实时状态指示灯（idle/running/completed）
- **底部输入栏**：支持多行输入，Enter 发送

---

## 开发状态

当前版本: **v0.2.0-dev**

| 模块 | 状态 |
|------|------|
| Protocol & Types | ✅ 完成 |
| Agent Registry + Capability Matching | ✅ 完成 |
| Orchestrator + TaskAnalyzer | ✅ 完成 |
| Workflow Engine (3 workflows) | ✅ 完成 |
| Collaboration Bus | ✅ 完成 |
| LLM Provider Layer (4 providers) | ✅ 完成 |
| Agent Runtime (sandbox, pool, executor, stream) | ✅ 完成 |
| Permission System (Plan/Agent/Auto) | ✅ 完成 |
| GUI Desktop Application | ✅ 完成 |
| TUI Terminal Dashboard | ✅ 完成 |
| Parallel Orchestration Engine | 🚧 进行中 |
| Agent Marketplace | 📋 计划中 |

---

## License

MIT License — 详见 [LICENSE](LICENSE)

---

<div align="center">

**OmniAgent Studio** — *让一百个 Agent 为你协作*

</div>
