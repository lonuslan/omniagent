# OmniAgent Studio — 开发计划与实施路线

> 参考项目：[DeepSeek-TUI](https://github.com/Hmbown/DeepSeek-TUI) (11.6k⭐) | 版本: 0.1.0-dev | 制定日: 2026-05-08

---

## 一、竞品分析：DeepSeek-TUI 的功能对照

DeepSeek-TUI 是目前最成功的终端 AI 编程 Agent，我们必须理解它的能力边界，才能做出超越它的东西。

### 1.1 DeepSeek-TUI 已实现的功能

| 分类 | 功能 | 技术实现 |
|------|------|----------|
| **交互模式** | Plan(只读) / Agent(确认) / YOLO(全自动) | 三种权限策略 |
| **工具系统** | 文件读写编辑、Shell执行、Git管理、Web搜索 | 类型化工具注册表 |
| **Sub-agent** | 7种角色子代理 (general/explore/plan/review/implement/verifier/custom) | 子任务委派 |
| **RLM并行** | 1个主模型并发调度最多16个Flash子任务 | 并行推理降本 |
| **MCP协议** | 完整的MCP客户端/服务端实现 | Model Context Protocol |
| **Skills系统** | 可组合安装的指令包 (SKILL.md)，社区注册表 | 文件系统扫描 + GitHub安装 |
| **LSP诊断** | rust-analyzer/pyright/typescript等原生集成 | 编辑后自动诊断注入上下文 |
| **1M上下文** | 100万token上下文窗口，智能压缩 | 前缀缓存感知 |
| **Thinking流** | 实时显示模型思维链、推理强度切换 | SSE流式渲染 |
| **会话管理** | 保存/恢复/分叉/回滚 | SQLite持久化 |
| **Git快照** | 独立于.git的side-git快照系统 | 操作级回滚 |
| **任务队列** | 持久化后台任务，重启可恢复 | 本地队列持久化 |
| **成本追踪** | 逐轮次token用量与费用，缓存命中率 | 实时统计 |
| **多语言UI** | en/ja/zh/pt-BR自动检测 | i18n |

### 1.2 DeepSeek-TUI 的局限性（OmniAgent 的机会）

| 局限 | DeepSeek-TUI 现状 | OmniAgent 方案 |
|------|------------------|----------------|
| **单Agent架构** | 1个主模型调度子任务，本质是1主多从 | **多Agent对等协作**，每个Agent都是独立个体 |
| **Agent选择靠人工** | 子代理需手动指定或由主模型决定 | **自主能力匹配**，系统自动分析任务并选择最优Agent |
| **仅限编程** | 工具链和模式都围绕代码设计 | **跨领域通用**，同一编排引擎适用于视频/文档/数据 |
| **终端束缚** | 只有TUI界面 | **Desktop UI** (Electron) + TUI + Web Dashboard |
| **封闭生态** | Skills安装靠GitHub URL手动指定 | **Marketplace** 自动发现、评分、安装 |
| **无Agent间通信** | 主模型单向分配，子代理间不通信 | **Collaboration Bus** 支持Agent间消息、Handoff、协商 |
| **无自定义Agent** | custom子代理配置有限 | **Agent Builder** 可视化创建+Python SDK |
| **单项目视角** | 专注于当前目录 | **多项目管理** + 跨项目知识共享 |

---

## 二、OmniAgent 开发阶段总览

```
Phase 1:  Foundation     Phase 2:  Runtime        Phase 3:  Platform        Phase 4:  Ecosystem
[████████████░░░░░░░]   [████████░░░░░░░░░░░]    [██████░░░░░░░░░░░░░░]    [████░░░░░░░░░░░░░░]
 v0.1.0                 v0.3.0                    v0.6.0                    v0.9.0
 已完成                  2个月                       4个月                     6个月
```

---

## 三、Phase 1: Foundation（基础框架）✅ 已完成

### 已交付

- [x] `protocol.py` — 核心类型系统（AgentDescriptor, Task, SubTask, CollaborationMessage, AgentEvent）
- [x] `core/registry.py` — Agent注册中心 + 能力匹配评分算法
- [x] `core/orchestrator.py` — 任务编排器（分析→分解→分配→执行）
- [x] `core/workflow.py` — 工作流引擎（software/video/document三种内置流程）
- [x] `collaboration/bus.py` — 协作消息总线 + Handoff协议 + Request/Response模式
- [x] `agents/base.py` — Agent基类 + 工厂模式
- [x] `agents/builtin/` — 5个内置Agent（General/CodeGen/CodeReview/DocWriter/Test）
- [x] `tools/base.py` — 声明式工具框架（兼容Function Calling）
- [x] `tools/builtin/` — 文件操作工具集（Read/Write/Edit/Glob/Grep）
- [x] `cli.py` — CLI入口（start/run/agent/market命令）
- [x] 单元测试 + Demo示例

---

## 四、Phase 2: Runtime（运行时核心）🎯 当前重点

> 目标：让 Agent 真正"活起来" — 接入 LLM、在沙箱中执行、产生真实产出

### Milestone 2.1: LLM Provider 统一接入层

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M2.1.1 | 定义 `LLMProvider` 统一接口（支持同步/流式） | P0 | 2d |
| M2.1.2 | 实现 `MiMoProvider`（小米MiMo API接入） | P0 | 2d |
| M2.1.3 | 实现 `DeepSeekProvider`（DeepSeek V4 API接入） | P0 | 2d |
| M2.1.4 | 实现 `ClaudeProvider`（Anthropic API接入） | P1 | 1d |
| M2.1.5 | 实现 `OpenAIProvider`（GPT API接入） | P1 | 1d |
| M2.1.6 | Provider 负载均衡 + 故障转移 | P1 | 2d |
| M2.1.7 | 模型能力自动检测（context长度、工具调用、vision） | P2 | 1d |

**重难点**：
- 不同Provider的工具调用格式差异（Anthropic XML vs OpenAI JSON Schema vs DeepSeek Function Call）
- 流式输出的统一抽象（SSE vs WS vs 自定义协议）
- 1M token上下文的Prompt缓存策略

### Milestone 2.2: Agent 运行时沙箱

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M2.2.1 | `AgentRuntime` 沙箱环境（隔离文件系统访问） | P0 | 3d |
| M2.2.2 | `LLMPool` 模型池管理（并发Agent共享模型连接） | P0 | 2d |
| M2.2.3 | `ToolExecutor` 工具执行引擎（权限检查+审批流） | P0 | 3d |
| M2.2.4 | `EventStream` 事件流输出（实时推送Agent进度） | P0 | 2d |
| M2.2.5 | Agent超时/重试/熔断机制 | P1 | 2d |
| M2.2.6 | 沙箱资源限制（文件数、网络、进程数） | P2 | 2d |

**重难点**：
- 多个Agent同时运行时文件系统隔离（避免相互覆盖）
- 工具执行的权限分级（读文件无需审批，删文件必须审批）
- EventStream的背压处理（大量事件时不出OOM）

### Milestone 2.3: 多Agent并行编排

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M2.3.1 | 并行执行引擎（无依赖SubTask并发跑） | P0 | 3d |
| M2.3.2 | Agent间上下文传递（Handoff Context序列化） | P0 | 2d |
| M2.3.3 | 任务依赖拓扑排序 + 死锁检测 | P0 | 2d |
| M2.3.4 | Agent间协商机制（对产出有分歧时讨论达成一致） | P1 | 3d |
| M2.3.5 | 动态Agent扩缩（任务量大时自动增减Agent数） | P2 | 3d |

**重难点**：
- 并行执行时的一致性保证（Agent A改的文件，Agent B同时也在读）
- Handoff时上下文的裁剪策略（不能全传1M token，要智能摘要）
- 协商机制的Prompt设计（两个Agent如何有效讨论）

### Milestone 2.4: 权限与安全

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M2.4.1 | 三种执行模式：Plan(只读) / Agent(确认) / Auto(全自动) | P0 | 2d |
| M2.4.2 | 工具级权限控制（哪些工具需要用户审批） | P0 | 2d |
| M2.4.3 | 文件范围限制（Agent只能访问指定目录） | P1 | 2d |
| M2.4.4 | 操作审计日志（谁在什么时候做了什么） | P1 | 2d |

---

## 五、Phase 3: Platform（平台化）📋 规划中

> 目标：从代码库变成真正的桌面产品

### Milestone 3.1: TUI 终端界面

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M3.1.1 | 基于 Python `textual` 框架的终端UI | P0 | 5d |
| M3.1.2 | 多面板布局（Agent列表/任务进度/事件流/终端） | P0 | 3d |
| M3.1.3 | 键盘快捷键系统（vim风格导航） | P1 | 2d |
| M3.1.4 | Thinking流式渲染（实时显示Agent思维链） | P0 | 3d |
| M3.1.5 | 成本实时追踪面板（token用量、费用、缓存命中率） | P1 | 2d |
| M3.1.6 | 会话持久化与恢复（SQLite） | P1 | 3d |

**参考 DeepSeek-TUI ratatui 的交互设计，但用 Python textual 实现，更易扩展**

### Milestone 3.2: Desktop 桌面应用

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M3.2.1 | Electron + React 桌面壳 | P0 | 5d |
| M3.2.2 | Web Dashboard（项目总览、Agent管理、任务监控） | P0 | 5d |
| M3.2.3 | 可视化 Workflow Builder（拖拽创建自定义工作流） | P1 | 5d |
| M3.2.4 | 可视化 Agent Builder（配置提示词、工具、模型） | P1 | 4d |
| M3.2.5 | 多项目管理（切换项目、跨项目知识库） | P2 | 3d |

### Milestone 3.3: 工具系统扩展

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M3.3.1 | LSP诊断集成（Python/Rust/TS/Go） | P1 | 4d |
| M3.3.2 | MCP协议客户端（对接外部MCP Server） | P0 | 3d |
| M3.3.3 | MCP协议服务端（让其他工具调用OmniAgent） | P2 | 3d |
| M3.3.4 | Git深度集成（diff/stash/branch/patch） | P1 | 3d |
| M3.3.5 | Web搜索 + URL内容提取 | P1 | 2d |
| M3.3.6 | 图片/视频分析工具 | P2 | 3d |

---

## 六、Phase 4: Ecosystem（开放生态）🌍 远期

> 目标：从工具变成平台

### Milestone 4.1: Agent Marketplace

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M4.1.1 | Marketplace API服务（Agent/Skill发布/搜索/安装） | P1 | 5d |
| M4.1.2 | GitHub Agent仓库索引（自动发现社区Agent） | P1 | 3d |
| M4.1.3 | Agent评分与评论系统 | P2 | 3d |
| M4.1.4 | 一键安装：`omniagent market install <agent-id>` | P1 | 2d |

### Milestone 4.2: Skill 生态

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M4.2.1 | SKILL.md 规范定义（OmniAgent版） | P1 | 2d |
| M4.2.2 | Skill 发现与加载（多路径扫描） | P1 | 2d |
| M4.2.3 | Skill 社区注册表（类似 DeepSeek-TUI 的 /skills sync） | P2 | 3d |
| M4.2.4 | 从 GitHub URL 安装 Skill | P1 | 1d |

### Milestone 4.3: 企业版

| ID | 任务 | 优先级 | 预估 |
|----|------|--------|------|
| M4.3.1 | RBAC权限系统（谁可以创建/管理Agent） | P2 | 4d |
| M4.3.2 | 审计日志持久化+查询 | P2 | 3d |
| M4.3.3 | 私有Marketplace（企业内部Agent目录） | P2 | 4d |
| M4.3.4 | SSO/LDAP集成 | P2 | 3d |

---

## 七、核心技术难点分析

### 难点 1: 自主Agent选择的准确性

**问题**：如何保证系统选出的Agent真正适合当前子任务？
**影响**：选错了Agent，整个流程的输出质量会严重下降。
**方案**：
- 能力匹配算法（已实现基础版）+ 语义相似度增强
- 引入"Agent信誉分"（历史任务成功率、用户评分）
- 支持用户在分配阶段手动调整

### 难点 2: 多Agent上下文一致性

**问题**：Agent A 修改了文件，Agent B 如何感知？Handoff时传递多少上下文？
**影响**：信息丢失导致后续Agent工作在错误基础上。
**方案**：
- 文件系统Watcher（监控Agent的写入操作）
- 上下文摘要策略（用LLM对前序工作做智能摘要再传递）
- 共享工作空间（Agent间通过明确的消息传递同步状态）

### 难点 3: Agent间协商机制

**问题**：CodeGenAgent 和 CodeReviewAgent 对代码方案有分歧，如何达成一致？
**影响**：这是多Agent系统最前沿的挑战，目前业界无成熟方案。
**方案**：
- 结构化辩论协议（提出观点→证据→反驳→裁决）
- 引入"仲裁Agent"角色
- 最终由用户决策

### 难点 4: 跨领域Workflow的通用性

**问题**：同样的编排引擎如何同时服务软件开发和视频制作？
**影响**：如果每个领域都要定制代码，就不是真正的"通用"平台。
**方案**：
- Workflow DSL（声明式工作流描述语言）
- 领域适配层（软件/视频/文档有各自的SubTask生成器）
- 用户可自定义Workflow（拖拽+配置）

### 难点 5: 工具调用的跨模型兼容

**问题**：不同LLM Provider的工具调用格式不同，如何统一？
**影响**：更换模型可能导致Agent无法使用工具。
**方案**：
- 统一工具描述中间层（OmniAgent ToolDescriptor → Provider特定格式）
- 自动适配器（检测模型支持的格式，自动转换）
- 优先支持Function Calling标准

### 难点 6: 实时协作的并发控制

**问题**：多个Agent同时读写文件，如何避免冲突？
**影响**：数据损坏、Agent读到过期内容。
**方案**：
- 乐观锁 + 版本号（类似Git的merge冲突检测）
- 文件租约机制（Agent需获取租约才能写入）
- 冲突时自动触发合并（简单冲突）或人工解决（复杂冲突）

---

## 八、技术选型决策

| 决策点 | 方案A | 方案B | 推荐 |
|--------|-------|-------|------|
| 核心语言 | Python（当前） | Rust（重写） | **Python** → Phase 4考虑性能热点用Rust重写 |
| TUI框架 | textual | ratatui (Rust) | **textual**（Python原生，开发效率高） |
| 桌面端 | Electron + React | Tauri + React | **Electron**（先快速出产品，后续切Tauri） |
| Agent间通信 | Python asyncio Queue | Redis Pub/Sub | **asyncio Queue**（单机够用，后续扩展Redis） |
| 持久化 | SQLite | PostgreSQL | **SQLite**（本地优先，企业版加PG） |
| LLM接入 | 自建Provider抽象 | LiteLLM / LangChain | **自建Provider**（更可控，参考DeepSeek-TUI做法） |

---

## 九、当前优先级排序（接下来2周）

```
P0 (必须完成):
  1. LLMProvider统一接入层 (M2.1.1 ~ M2.1.3)
  2. AgentRuntime沙箱 (M2.2.1 ~ M2.2.4)
  3. 并行执行引擎 (M2.3.1 ~ M2.3.3)

P1 (尽快完成):
  4. 三种执行模式 (M2.4.1)
  5. 工具权限控制 (M2.4.2)
  6. ClaudeProvider + OpenAIProvider (M2.1.4 ~ M2.1.5)

P2 (时间允许):
  7. TUI界面调研 (M3.1)
  8. LSP集成调研 (M3.3.1)
```

---

## 十、里程碑与交付物

| 版本 | 日期 | 核心交付 |
|------|------|----------|
| v0.1.0 ✅ | 2026-05-08 | Protocol + Registry + Orchestrator + Workflow + Collab Bus |
| v0.2.0 | 2026-05-16 | LLM Provider层 + Agent Runtime + 第一个真实Agent运行 |
| v0.3.0 | 2026-05-24 | 并行编排 + 多Agent协作Demo + TUI原型 |
| v0.4.0 | 2026-06-07 | 完整TUI + 权限系统 + 会话持久化 |
| v0.5.0 | 2026-06-21 | MCP集成 + Git深度集成 + LSP诊断 |
| v0.6.0 | 2026-07-12 | Desktop壳 + Web Dashboard |
| v0.7.0 | 2026-08-02 | Workflow Builder + Agent Builder |
| v0.8.0 | 2026-08-23 | Marketplace服务 + Skill安装 |
| v0.9.0 | 2026-09-20 | 企业版功能 |
| v1.0.0 | 2026-10-18 | 正式发布 |

---

*本文档会随着开发进展持续更新。下一步：请确认优先级的Task列表，我来转化为具体的Todo项。*
