# OmniAgent Studio

<div align="center">

**自主多Agent协同通用平台 | Autonomous Multi-Agent Collaborative Platform**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Pre-Alpha](https://img.shields.io/badge/status-pre--alpha-orange.svg)]()

*一个 Agent 做一件事，一百个 Agent 协作完成一个项目*

</div>

---

## 这是什么？

**OmniAgent Studio** 是一个全新的多 Agent 协同工作平台。它的核心理念是：

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

---

## 核心能力

### 🧠 自主任务编排

```
用户: "帮我开发一个电商网站"

Orchestrator 自动分析:
  ├─ 领域识别: software → 使用 software_lifecycle 工作流
  ├─ 任务分解:
  │   ├─ [需求确认] → GeneralAgent
  │   ├─ [需求分析] → DocWriterAgent + GeneralAgent
  │   ├─ [原型设计] → CodeGenAgent (UI focus)
  │   ├─ [前端开发] → CodeGenAgent (React/TypeScript)
  │   ├─ [后端开发] → CodeGenAgent (Python/FastAPI)
  │   ├─ [测试]     → TestAgent + CodeReviewAgent
  │   └─ [部署]     → GeneralAgent (deploy config)
  └─ 按依赖顺序并行/串行执行
```

### 🌐 跨领域通用

同一套编排引擎，适用于完全不同的领域：

| 领域 | Workflow 阶段 | 涉及 Agent |
|------|--------------|-----------|
| 🖥️ 软件开发 | 需求→分析→原型→前端→后端→测试→部署 | CodeGen, Review, Test, Doc |
| 🎬 视频制作 | 脚本→素材→剪辑→音频→转场→审阅→导出 | Video, Audio, Copywriting |
| 📝 文档写作 | 大纲→初稿→审阅→定稿 | Documentation, Copywriting |
| 📊 数据分析 | 采集→清洗→分析→可视化 | DataAnalysis, Visualization |

### 🔌 三源 Agent 生态

```
builtin (内置)          custom (自定义)         marketplace (社区)
    │                       │                       │
    ├─ GeneralAgent         ├─ 通过 CLI 创建        ├─ GitHub Agent 仓库
    ├─ CodeGenAgent         ├─ 通过 UI Builder      ├─ Community Hub
    ├─ CodeReviewAgent      ├─ Python SDK 继承      ├─ Enterprise Catalog
    ├─ DocWriterAgent       └─ 声明式配置            └─ 一行命令安装
    └─ TestAgent
```

### 🛠️ 完整的工具系统

类似 Claude Code 的工具框架，任何 Agent 都可以使用：

- **文件操作**: Read, Write, Edit, Glob, Grep
- **Shell 执行**: 运行命令、脚本
- **Web 访问**: Fetch, Search
- **Agent 管理**: Spawn sub-agent, Handoff task

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-org/omniagent.git
cd omniagent
pip install -e ".[dev]"
```

### 运行 Demo

```bash
# 软件开发全流程 Demo
python examples/demo_software_project.py

# 视频制作全流程 Demo
python examples/demo_video_production.py
```

### CLI 使用

```bash
# 列出所有可用 Agent
omniagent agent list

# 运行一个任务
omniagent run "Build a REST API for a blog platform"

# 搜索 Marketplace
omniagent market search "video editing agent"
```

### 运行测试

```bash
pytest tests/ -v
```

---

## 系统架构

详细架构请参阅 [ARCHITECTURE.md](ARCHITECTURE.md)

```
┌─────────────────────────────────────────────────────────┐
│                    OmniAgent Studio                       │
├─────────────────────────────────────────────────────────┤
│  CLI / Desktop UI / Web Dashboard                        │
├─────────────────────────────────────────────────────────┤
│  Orchestrator (任务分析 → 能力匹配 → Agent分配)           │
├─────────────────────────────────────────────────────────┤
│  Registry │ Workflow Engine │ Collaboration Bus │ Tools  │
├─────────────────────────────────────────────────────────┤
│  Agent Runtime (沙箱隔离 │ LLM 模型池 │ 工具执行)         │
├─────────────────────────────────────────────────────────┤
│  Builtin Agents │ Custom Agents │ Marketplace Agents     │
└─────────────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Protocol** | `protocol.py` | 核心类型、消息格式、Agent 协议 |
| **Registry** | `core/registry.py` | Agent 注册、发现、能力匹配评分 |
| **Orchestrator** | `core/orchestrator.py` | 任务分析、分解、Agent 选择、执行协调 |
| **Workflow** | `core/workflow.py` | 多阶段工作流模板（软件/视频/文档） |
| **Collaboration** | `collaboration/bus.py` | Agent 间消息总线、Handoff 协议 |
| **Tools** | `tools/base.py` | 声明式工具框架，兼容 Function Calling |

### 内置 Agent

| Agent | ID | 能力 |
|-------|-----|------|
| General Purpose Agent | `general-agent` | 通用任务处理、需求澄清 |
| Code Generation Agent | `code-gen-agent` | 前后端代码生成 (React, Python, Go...) |
| Code Review Agent | `code-review-agent` | 代码审查、安全审计、性能分析 |
| Documentation Writer | `doc-writer-agent` | 文档、报告、文案生成 |
| Test Agent | `test-agent` | 测试用例生成和执行 |

---

## 路线图

- [x] **Phase 1: Foundation** — 核心协议、Registry、Orchestrator、Workflow、Collaboration Bus、Tool System
- [ ] **Phase 2: Runtime** — Agent 沙箱执行、LLM Provider 接入、真实 Agent 运行
- [ ] **Phase 3: Platform** — Desktop UI (Electron)、Agent Builder、Workflow Builder
- [ ] **Phase 4: Ecosystem** — Marketplace 服务、Agent 分享安装、社区治理

---

## 项目意义

OmniAgent Studio 探索的是 **AI Agent 协作的下一阶段**：

1. **从单 Agent 到多 Agent**：单个 Agent 的能力有限，真正的复杂项目需要多个 Agent 各司其职
2. **从人工编排到自主编排**：不再需要手动指定"用这个 Agent 做 X"，系统自动分析并选择
3. **从垂直工具到通用平台**：不仅限于编程，任何可以分解为阶段流程的创造性工作都能受益
4. **从封闭到开放生态**：Agent 和 Skill 可以来自社区，可发现、可安装、可组合

这是一个长期项目，将随着 AI 模型能力的提升而不断进化。

---

## 贡献

欢迎贡献！请先阅读我们的贡献指南（待完善）。

- 🐛 Bug 报告：[GitHub Issues](#)
- 💡 功能建议：[GitHub Discussions](#)
- 🔧 代码贡献：Fork → Branch → PR

---

## License

MIT License - 详见 [LICENSE](LICENSE)

---

<div align="center">

**OmniAgent Studio** — *让一百个 Agent 为你协作*

</div>
