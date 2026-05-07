# OmniAgent Studio — 系统架构设计

> **版本**: 0.1.0 | **状态**: Pre-Alpha | **最后更新**: 2026-05-08

## 1. 项目愿景

OmniAgent Studio 是一个**自主多Agent协同通用平台**。它不只是另一个 AI 编程工具——它的核心创新在于：

1. **自主Agent选择**：系统自动分析任务语义，从注册中心选择最合适的 Agent 执行
2. **跨领域通用**：同一套编排引擎，适用于软件开发、视频制作、文档写作、数据分析等
3. **真实开发流程**：内置专业的 Workflow 模板（需求→设计→编码→测试→部署），模拟真实项目开发
4. **开放生态**：支持从社区 Marketplace 发现和安装 Agent/Skill，也可以自定义创建

## 2. 核心设计理念

### 2.1 "Director + Actors" 模式

```
                    ┌─────────────┐
                    │  用户任务    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Orchestrator │  ← "导演"：分析、分解、分配
                    │  + Analyzer  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ Agent A   │ │Agent B │ │ Agent C  │  ← "演员"：各司其职
        │ (前端)    │ │(后端)  │ │ (测试)   │
        └───────────┘ └────────┘ └──────────┘
              │            │            │
              └────────────┼────────────┘
                           │
                    ┌──────▼──────┐
                    │Collaboration│  ← 协作总线
                    │    Bus      │
                    └─────────────┘
```

### 2.2 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Agent 通信协议 | 异步消息总线 + 事件流 | 支持并行执行、松耦合、可回放审计 |
| Agent 发现机制 | 能力匹配评分算法 | 自动选择最优 Agent，无需手动指定 |
| Workflow 引擎 | 阶段式模板 + 依赖拓扑排序 | 支持复杂依赖关系，并行执行无依赖阶段 |
| 工具系统 | 声明式 ToolDescriptor | 兼容 LLM Function Calling，可被任何 Agent 使用 |
| 扩展性 | Provider 模式（builtin/custom/marketplace） | 开放生态，社区可贡献 |

## 3. 系统架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                         OmniAgent Studio                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │   CLI    │  │  Desktop │  │   API    │  │   Web Dashboard  │ │
│  │ (Typer)  │  │(Electron)│  │ (FastAPI)│  │   (React/Plan)   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘ │
│       └──────────────┴─────────────┴─────────────────┘           │
│                            │                                       │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │                    Orchestrator (编排层)                     │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │  │
│  │  │ TaskAnalyzer │  │AgentSelector │  │ ResultAggregator │  │  │
│  │  │ (任务分析)    │  │ (能力匹配)    │  │ (结果聚合)       │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │                   Core Services (核心服务)                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐ │  │
│  │  │ Registry │ │ Workflow │ │Collab Bus│ │ Tool Registry │ │  │
│  │  │(Agent注册)│ │(工作流)   │ │(协作总线) │ │  (工具注册)   │ │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘ │  │
│  └─────────────────────────┬──────────────────────────────────┘  │
│                            │                                       │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │                    Agent Runtime (代理运行时)                 │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐ │  │
│  │  │ Sandbox  │ │ LLM Pool │ │Tool Exec │ │ Event Stream  │ │  │
│  │  │(沙箱隔离) │ │(模型池)   │ │(工具执行) │ │  (事件流)     │ │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘ │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

## 4. 核心模块详解

### 4.1 Orchestrator（编排器）

**核心职责**：接收用户任务，自动分析、分解、分配、执行。

```
用户提交任务
    │
    ▼
TaskAnalyzer.analyze()
    │  分析描述文本 → 识别领域(software/video/document)
    │  推断所需能力 → [CODE_GENERATION, TESTING, ...]
    │  建议工作流   → "software_lifecycle"
    │
    ▼
Workflow.generate_sub_tasks()
    │  按阶段分解 → [需求确认, 需求分析, 原型设计, ...]
    │  建立依赖关系 → 需求分析 depends_on 需求确认
    │
    ▼
AgentSelector (Registry.find_best)
    │  对每个子任务，计算所有 Agent 的匹配分数
    │  选择最高分的 Agent
    │
    ▼
Parallel / Sequential Execution
    │  拓扑排序 → 无依赖的子任务并发执行
    │  有依赖关系的按序执行
    │
    ▼
Result Aggregation → 返回用户
```

**能力匹配算法**：

```python
def capability_match_score(required, offered):
    matched = set(required) & set(offered)
    precision = len(matched) / len(required)
    extra = len(set(offered) - set(required)) * 0.05  # 额外能力小加分
    return min(1.0, precision + extra)
```

### 4.2 Agent Registry（注册中心）

管理所有 Agent 的生命周期。三源架构：

- **builtin**：系统内置的通用 Agent（代码生成、审查、文档、测试）
- **custom**：用户通过 UI/CLI 自定义的 Agent
- **marketplace**：从社区 Marketplace 发现和安装的 Agent

支持动态注册/注销，按能力和角色多维度索引。

### 4.3 Workflow Engine（工作流引擎）

将抽象的任务分解为可执行的阶段序列。内置三种专业 Workflow：

| Workflow | 阶段数 | 适用场景 |
|----------|--------|----------|
| `software_lifecycle` | 7 | 需求→分析→原型→前端→后端→测试→部署 |
| `video_production` | 7 | 脚本→素材→剪辑→音频→转场→审阅→导出 |
| `document_writing` | 4 | 大纲→初稿→审阅→定稿 |

用户可注册自定义 Workflow。

### 4.4 Collaboration Bus（协作总线）

Agent 间通信的基础设施：

- **消息路由**：点对点和广播模式
- **Agent Handoff 协议**：一个 Agent 完成后将上下文传递给下一个
- **Request/Response 模式**：Agent A 向 Agent B 请求信息
- **事件流**：每个 Task 有独立的事件流，支持实时监控和历史回放

### 4.5 Tool System（工具系统）

受 Claude Code 工具系统启发，提供声明式的工具框架：

- 每个工具通过 `ToolDescriptor` 声明名称、描述、参数
- 兼容 LLM Function Calling 格式
- 分类管理：file、shell、web、agent
- 支持权限控制（requires_approval）

## 5. Agent 通信协议

### 5.1 Agent 自描述

每个 Agent 必须声明：

```python
AgentDescriptor(
    id="code-gen-agent",
    name="Code Generation Agent",
    capabilities=[CODE_GENERATION, UI_DESIGN],
    role=AgentRole.EXECUTOR,
    model_requirements=["claude-sonnet-4-6"],
)
```

### 5.2 消息格式

```python
CollaborationMessage(
    id="msg-001",
    sender_id="code-gen-agent",
    receiver_id="code-review-agent",  # None = broadcast
    message_type="handoff",
    payload={"task_id": "...", "context": {...}},
    reply_to=None,  # 回复某条消息时填写
)
```

### 5.3 Agent 生命周期

```
register → initialize → [execute → review]* → cleanup → unregister
```

## 6. 扩展性设计

### 6.1 自定义 Agent

用户可以通过以下方式创建自定义 Agent：

1. **CLI**：`omniagent agent create --name "my-agent" --capability "data_analysis"`
2. **Python SDK**：继承 `BaseAgent`，实现 `_do_execute()`
3. **UI Builder**（规划中）：可视化配置 Agent 的提示词、工具、模型

### 6.2 Marketplace 集成

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OmniAgent  │────▶│ Marketplace API  │────▶│  GitHub Registry │
│   Studio    │     │  (统一接口)       │     │  (Agent 仓库)   │
└─────────────┘     └──────────────────┘     └─────────────────┘
       │                     │
       │                     ├── Community Hub
       │                     ├── Enterprise Catalog
       │                     └── Custom Sources
       │
       ▼
  Agent installed & registered
```

## 7. 技术栈

| 层 | 技术选择 | 说明 |
|----|----------|------|
| 核心语言 | Python 3.11+ | Agent 逻辑、编排、协议 |
| 桌面端 | Electron + React (规划) | 跨平台桌面应用 |
| Web UI | React + Vite + Tailwind | 仪表盘和管理界面 |
| 通信 | WebSocket + HTTP | 实时事件推送 |
| 数据 | SQLite (本地) + JSON | 任务历史、Agent 配置 |
| 沙箱 | Docker / WASM (规划) | Agent 执行隔离 |
| LLM 接入 | 统一 Provider 接口 | 支持 MiMo、Claude、GPT 等 |

## 8. 路线图

### Phase 1: Foundation (当前)
- [x] 核心协议定义（Protocol）
- [x] Agent Registry + 能力匹配
- [x] Orchestrator + TaskAnalyzer
- [x] Workflow Engine（3种内置工作流）
- [x] Collaboration Bus
- [x] Tool System + 内置文件工具
- [x] 5个内置 Agent
- [x] CLI 入口

### Phase 2: Runtime (进行中)
- [ ] Agent Runtime 沙箱
- [ ] LLM Provider 统一接入（MiMo、Claude、GPT）
- [ ] 真实 LLM 驱动的 Agent 执行
- [ ] Agent 间上下文传递和记忆

### Phase 3: Platform
- [ ] Desktop UI（Electron）
- [ ] Web Dashboard
- [ ] Agent Builder（可视化创建 Agent）
- [ ] Workflow Builder（可视化创建工作流）

### Phase 4: Ecosystem
- [ ] Marketplace 服务和发现协议
- [ ] Agent 分享和安装
- [ ] 社区贡献指南
- [ ] 企业版功能（RBAC、审计日志）

## 9. 项目结构

```
omniagent/
├── src/omniagent/
│   ├── protocol.py          # 核心类型和协议定义
│   ├── cli.py               # CLI 入口
│   ├── core/
│   │   ├── registry.py      # Agent 注册中心
│   │   ├── orchestrator.py  # 任务编排器
│   │   └── workflow.py      # 工作流引擎
│   ├── agents/
│   │   ├── base.py          # Agent 基类
│   │   └── builtin/         # 内置 Agent
│   ├── tools/
│   │   ├── base.py          # Tool 框架
│   │   └── builtin/         # 内置工具
│   └── collaboration/
│       └── bus.py           # 协作消息总线
├── tests/                   # 单元测试
├── examples/                # 示例演示
├── docs/design/             # 设计文档
├── ARCHITECTURE.md          # 本文档
└── README.md                # 项目说明
```
