# 企业级 Agent 平台技术选型报告

> **日期**: 2026-07-25
> **目的**: 评估 LangChain Deep Agents 与 Claude Agent SDK 两种方案，为企业级 Agent 平台选择核心技术栈。

---

## 目录

1. [需求概述](#1-需求概述)
2. [方案一：LangChain Deep Agents](#2-方案一langchain-deep-agents)
3. [方案二：Claude Agent SDK](#3-方案二claude-agent-sdk)
4. [逐项对比分析](#4-逐项对比分析)
5. [综合评分矩阵](#5-综合评分矩阵)
6. [选型结论与建议](#6-选型结论与建议)
7. [推荐架构蓝图](#7-推荐架构蓝图)
8. [风险与注意事项](#8-风险与注意事项)

---

## 1. 需求概述

需要构建一个 **BS 架构、支持多用户并发** 的通用企业 Agent 平台，核心能力需求分为两个层面：

### 通用 Agent 能力

| 能力 | 描述 |
|------|------|
| 工具调用 (Tool Calling) | 支持 Agent 调用外部 API、函数、服务 |
| 多轮对话 | 有状态的上下文对话管理 |
| 任务编排 | 复杂任务的分解、调度、并行执行 |
| 多 Agent 协作 | 多个 Agent 之间的委托、协商、编排 |
| Skill 创建与调用 | 可复用的技能模块封装与动态加载 |
| MCP 创建与调用 | Model Context Protocol 服务端/客户端集成 |
| 知识库检索 (RAG) | 向量检索、混合搜索、文档问答 |

### 企业级特性

| 能力 | 描述 |
|------|------|
| 数据隔离 | 多租户/多用户数据严格隔离 |
| 数据安全 | 敏感信息过滤、PII 检测、访问控制 |
| 安全围栏 (Guardrails) | 输入/输出内容审核、工具调用拦截 |
| 人机协同 (HITL) | 关键操作的人工审批、中断恢复 |
| 长短期记忆 | 跨会话持久记忆 + 会话内短期上下? |
| 断点持久化 | Agent 执行状态检查点、故障恢复 |
| 可观测性 | 全链路追踪、成本监控、执行审计 |

---

## 2. 方案一：LangChain Deep Agents

### 2.1 概述

LangChain Deep Agents 是 LangChain 推出的 **"电池全装"式 Agent 运行框架**（opinionated agent harness），基于 LangGraph 构建，专为长周期、多步骤、生产级 Agent 场景设计。已经在 Rippling、OpenSWE、LangChain 内部 GTM Agent 等场景落地验证。

- **许可协议**: MIT
- **语言**: Python / TypeScript
- **GitHub**: [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents)
- **最新版本**: v0.5 (2026年4月)

### 2.2 核心架构

```
┌─────────────────────────────────────────────────┐
│                 Deep Agents Harness               │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │  Middleware │ │  Skills  │ │  Sub-agents      │  │
│  │  Stack    │ │  (SKILL) │ │  (inline/async)   │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │  Context  │ │  Memory  │ │  Filesystem       │  │
│  │  Manager  │ │  (Store) │ │  Backend          │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────────┐ │
│  │              LangGraph Runtime                │ │
│  │  ┌─────────┐  ┌──────────┐  ┌─────────────┐ │ │
│  │  │ Checkpoint│  │ Streaming │  │ Interrupt   │ │ │
│  │  │ (PG)     │  │ Endpoints │  │ (HITL)      │ │ │
│  │  └─────────┘  └──────────┘  └─────────────┘ │ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 2.3 各需求能力评估

#### 通用 Agent 能力

**工具调用** ✅ 优秀
- 内置工具层支持自定义函数、API、MCP Server
- 沙箱化代码执行（Shell 命令 + QuickJS JavaScript 解释器）
- 通过 Middleware 可以在工具调用任意阶段注入逻辑

**多轮对话** ✅ 优秀
- LangGraph 的 Thread 机制天然支持有状态对话
- `thread_id` 级别的状态隔离，支持对话历史持久化
- 自动摘要压缩，避免 Token 超限

**任务编排** ✅ 优秀
- 内置 `write_todos` 工具进行结构化任务跟踪
- LangGraph 的 DAG 状态图支持复杂分支、条件路由
- 支持并行节点执行和条件分支的推测执行（LangGraph Accelerated）

**多 Agent 协作** ✅ 优秀
- 三种子 Agent 模式：
  - **Inline subagent**: 阻塞式，父 Agent 等待结果
  - **Compiled subagent**: 编译为专注特定任务的受限工具集
  - **Async subagent** (v0.5): 非阻塞、有状态，在独立服务器上并行运行
- 支持子 Agent 使用不同的模型提供商
- 支持嵌套子 Agent

**Skill 创建与调用** ✅ 优秀
- 原生 Skill 系统：`SKILL.md` 文件（YAML frontmatter + Markdown 指令）
- 渐进式披露机制（只在需要时读取），节省上下文空间
- 技能可以被 Agent 自主发现和调用

**MCP 创建与调用** ✅ 优秀
- 完整支持 Model Context Protocol
- 可作为 MCP Client 连接外部 MCP Server
- 部署时自动暴露 MCP 端点供外部调用

**知识库检索 (RAG)** ✅ 优秀
- 通过 Store 接口与向量数据库集成（PostgreSQL + pgvector 为默认后端）
- 支持语义搜索和 Embedding 配置
- 可通过 CompositeBackend 将知识库映射为虚拟文件系统路径

#### 企业级特性

**数据隔离** ✅ 优秀（内置）
- 内置多租户支持：作用域化的 Thread、每用户 Sandbox、RBAC
- `langgraph build` 产出的 Docker 镜像天然支持多租户部署
- LangSmith Sandbox 提供 Auth Proxy，无需为每用户配置凭证

**数据安全** ✅ 良好
- PII 检测 Middleware：支持 `redact`/`mask`/`hash`/`block` 策略
- FilesystemMiddleware 基于 Glob 模式的细粒度权限控制
- 路径遍历防护（阻止 `..` 和 `~` 逃逸）
- Unicode 安全防护（控制字符清理、同形异义字攻击防御）
- Sandbox 级别的沙箱隔离

**安全围栏** ✅ 良好
- 多层 Guardrails 架构：
  - **前置 Guardrails**: 认证、速率限制、内容过滤（关键词/正则）
  - **后置 Guardrails**: LLM 安全评估、合规扫描
  - **确定性 Guardrails**: 基于规则的快速拦截
  - **模型 Guardrails**: LLM 分类器检测语义违规
- Middleware 链式堆叠，多层保护

**人机协同** ✅ 优秀
- 基于 LangGraph `interrupt` 的审批机制
- 四种决策类型：`approve`（批准）/ `edit`（编辑）/ `reject`（拒绝）/ `respond`（回复）
- 支持条件断点（根据工具参数决定是否需要审批）
- 暂停后可释放资源，恢复时从检查点精确继续
- 支持未来扩展：角色门控审批、多方审批 (M-of-N)

**长短期记忆** ✅ 优秀
- **短期记忆**: Thread 级别的检查点（对话消失则记忆消失）
- **长期记忆**: LangGraph Store（键值接口，按命名空间组织，默认 PostgreSQL 后端）
  - 按 User / Assistant / Organization 三级作用域
  - 支持语义搜索（通过 Embedding 配置）
  - 以虚拟文件系统方式暴露给 Agent（如 `/memories/` 路径）
- `MemoryMiddleware` 自动管理记忆的读写

**断点持久化** ✅ 优秀
- LangGraph 的 Durable Execution 是基础运行时能力
- 每个 super-step 写入检查点到 PostgreSQL
- 故障恢复：Worker 崩溃后另一 Worker 从最后检查点接管
- 时间旅行：可回退到任意历史检查点并分叉执行
- 暂停-恢复无时间限制（等待人工审批时释放 Worker 资源）

**可观测性** ✅ 优秀
- 与 LangSmith 深度集成：
  - 全链路分布式追踪（模型调用、工具调用、子 Agent 运行）
  - 按用户、时间窗口、成本、延迟、错误状态查询
  - 在线评估（Online Evals）自动检测生产回归
  - LangSmith Studio 可视化调试 + 时间旅行
- 部署时自动配置 Tracing Project
- OpenTelemetry 支持

### 2.4 部署方式

**双模式部署（无需代码变更）**:
- **托管模式**: `deepagents deploy` 一键部署到 LangSmith Deployment (LSD)，自动配置助理、线程、存储、检查点、认证、Webhook、定时任务
- **自托管模式**: `langgraph build` 生成独立 Docker 镜像，可部署到任意 K8s 环境

部署服务器自带 30+ 端点：流式传输、线程管理、运行历史、Webhook、认证、MCP、A2A、Agent Protocol。

### 2.5 生态与集成

- **模型**: 支持 100+ 模型提供商（Anthropic、OpenAI、Google、AWS Bedrock 等）
- **沙箱后端**: 本地、虚拟文件系统、远程沙箱、自定义后端
- **NVIDIA 集成**: NeMoClaw Blueprint（Nemotron 3 Ultra 优化，推理成本降低 10 倍）
- **Oracle 集成**: 统一数据库后端（向量、聊天历史、检查点、文档、关系数据）
- **开放协议**: MCP、A2A、Agent Protocol

### 2.6 优缺点总结

| 优点 | 缺点 |
|------|------|
| 模型无关，避免供应商锁定 | 学习曲线较陡（需理解 LangGraph 概念） |
| 内置多租户，无需自行构建 | 框架较 "重"，启动需要较多基础设施 |
| 双模式部署（托管/自托管）无缝切换 | 依赖 LangChain 生态，版本升级可能有 Breaking |
| 可观测性开箱即用（LangSmith） | LangSmith 托管服务有额外成本 |
| 记忆和持久化是框架一等公民 | 细粒度权限控制不如 Claude SDK 成熟 |
| Middleware 架构深度可定制 | 社区相对较新（v0.5，仍在快速迭代） |

---

## 3. 方案二：Claude Agent SDK

### 3.1 概述

Claude Agent SDK（前身为 Claude Code SDK，2025年底更名）是 Anthropic 推出的嵌入式 Agent SDK，将 Claude Code 的完整 Agent 循环（内置工具、子 Agent、Hooks、MCP 集成、会话管理）打包为 Python 和 TypeScript 库，允许开发者在自己的进程中运行 Claude 的自主 Agent 能力。

- **许可协议**: MIT（SDK 本身），Claude Code CLI 为专有软件
- **语言**: Python / TypeScript
- **文档**: [code.claude.com/docs/en/agent-sdk](https://code.claude.com/docs/en/agent-sdk)
- **最新进展**: Managed Agents 公测中 (2026)

### 3.2 核心架构

```
┌──────────────────────────────────────────────────┐
│           Your Application Process                │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │          Claude Agent SDK                    │ │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │ │
│  │  │ query()  │  │ Session  │  │ Hooks     │ │ │
│  │  │ API      │  │ Manager  │  │ (14+ 种)   │ │ │
│  │  └──────────┘  └──────────┘  └───────────┘ │ │
│  └──────────────────┬──────────────────────────┘ │
│                     │ stdio (JSON Protocol)        │
│  ┌──────────────────▼──────────────────────────┐ │
│  │        Claude Code CLI (子进程)              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │ │
│  │  │ Agent    │  │ Built-in │  │ MCP       │ │ │
│  │  │ Loop     │  │ Tools    │  │ Client    │ │ │
│  │  └──────────┘  └──────────┘  └───────────┘ │ │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐ │ │
│  │  │ Sub-     │  │ Skills   │  │ Context   │ │ │
│  │  │ agents   │  │ System   │  │ Manager   │ │ │
│  │  └──────────┘  └──────────┘  └───────────┘ │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  工作目录 (per-session):                           │
│  ~/.claude/projects/  (transcripts/artifacts)     │
└──────────────────────────────────────────────────┘
```

**关键架构特点**:
- SDK 调用 `query()` 时，启动一个 Claude Code CLI **子进程**，通过 stdio JSON 协议通信
- 每个 Agent 会话 = 一个子进程，有独立的进程树和会话转录文件 (JSONL)
- Agent 核心逻辑在 CLI 进程内运行，对开发者是 "灰盒"
- **只支持 "Agent 在沙箱内部" 的模式**（Agent 直接操作沙箱本地文件系统）

### 3.3 各需求能力评估

#### 通用 Agent 能力

**工具调用** ✅ 优秀
- 内置丰富的文件系统工具（Read、Write、Edit、Bash、Grep、Glob 等）
- 支持自定义工具（通过 MCP Server 或进程内函数）
- `canUseTool` 回调进行自定义授权
- 细粒度工具控制：`allowedTools`、`disallowedTools`、`permissionMode`

**多轮对话** ✅ 优秀
- SDK 的 `ClaudeSDKClient` 自动跟踪会话状态
- 会话转录持久化到本地 JSONL 文件
- 支持 Compaction（自动摘要压缩旧上下文）

**任务编排** ✅ 良好
- Agent 可以自主规划和分解任务
- Workflow 工具（TS SDK v0.3.149+）支持 JS 脚本编排
- 但缺乏 LangGraph 式的显式状态图编排能力

**多 Agent 协作** ✅ 良好
- 三种子 Agent 创建方式：
  - **编程式**: `AgentDefinition` 在 `query()` 选项中配置
  - **文件系统式**: `.claude/agents/` 目录下的 Markdown
  - **内置通用 Agent**: 通过 `Agent` 工具自主调用
- `AgentDefinition` 支持：背景执行、每 Agent 模型覆盖、工具限制、MCP Server 子集、Effort 调节
- 支持嵌套子 Agent（v2.1.172+，最多 5 层）
- Workflow 工具支持大规模编排（最多 16 并发、1000 Agent/次运行）
- Managed Agents 支持 Coordinator 模式的多 Agent 会话

**Skill 创建与调用** ✅ 优秀
- 文件系统式 Skill 系统：`SKILL.md`（YAML frontmatter + Markdown）
- 渐进式加载，避免上下文膨胀
- Agent 可自主发现和调用 Skill

**MCP 创建与调用** ✅ 优秀
- 完整 MCP Client 支持
- 工具命名模式: `mcp__<server>__<action>`，可通过 `^mcp__` 正则匹配
- 子 Agent 可配置每个 Agent 的 MCP Server 子集
- 动态 MCP Server 加载

**知识库检索 (RAG)** ⚠️ 需自行构建
- SDK 本身不内置向量存储或 RAG 管道
- 需通过 MCP Server 连接外部向量数据库（ChromaDB、pgvector 等）
- 需自行实现检索管道（查询路由、文档评分、重排序）
- 社区有 Adaptive RAG 等多 Agent RAG 参考架构
- 可以通过 Agent 内置的 Grep/Glob 工具做文件级搜索
- 总结：**有路径但需大量自定义开发**

#### 企业级特性

**数据隔离** ⚠️ 需大量自建
- SDK 不提供内置多租户
- 需自行实现：
  - 每租户独立工作目录（通过 `cwd` 参数）
  - 每租户独立配置目录（`CLAUDE_CONFIG_DIR`）
  - 禁用自动记忆注入（`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`）
  - 空的 `settingSources` 防止文件系统设置泄漏
- 社区推荐通过容器化 + Per-tenant Sandbox 实现隔离
- **无内置 RBAC**

**数据安全** ✅ 优秀
- 多层权限系统：
  - 权限模式: `default`、`acceptEdits`、`dontAsk`、`bypassPermissions`、`plan`
  - 工具级 deny/allow 规则
  - `canUseTool` 自定义授权回调
- 工具凭证管理：通过代理注入 API Key，不暴露给 Agent 环境
- 入站认证通过 Gateway 前置处理
- Sandbox 级别的进程隔离

**安全围栏** ✅ 优秀
- 14+ 生命周期 Hooks：

| Hook | 触发时机 |
|------|---------|
| PreToolUse | 工具调用前 — 阻断/修改/延迟 |
| PostToolUse | 工具返回后 — 注入上下文或替换输出 |
| PostToolUseFailure | 工具执行失败 |
| SubagentStart/Stop | 子 Agent 生命周期 |
| PreCompact | 对话即将被压缩 |
| Notification | Agent 状态事件 |
| PermissionRequest | 权限弹窗即将出现 |
| UserPromptSubmit | 提示词提交时注入上下文 |
| SessionStart/End | 会话生命周期 |

- 多个 PreToolUse Hooks 并行运行，否决即阻断
- 支持精确工具名、正则、MCP 全局匹配

**人机协同** ⚠️ 需自定义
- SDK 提供基础的 `needs_approval` 和 `RunState` resume 机制
- Permission Hooks 可以自定义审批流程
- 支持 `plan` 模式（先出计划，人工确认后执行）
- 但不像 LangChain 那样有开箱即用的审批-编辑-拒绝-回复完整决策类型
- **缺乏框架级的中断-持久化-恢复机制**

**长短期记忆** ⚠️ 需自行构建
- SDK 有 CLAUDE.md 文件作为持久化指令（项目级/用户级）
- 有自动记忆功能（`~/.claude/projects/` 下的项目记忆）
- **但缺乏跨会话的语义记忆 Store**
- 长期记忆需通过 MCP Server 或外部服务自行实现
- 社区方案（如 ruflo-rag-memory）通过 AgentDB + HNSW 实现跨会话语义检索

**断点持久化** ⚠️ 需自行构建
- SDK 会话转录存储在本地 JSONL 文件
- SessionStore 适配器（S3、Redis、Postgres）可镜像转录到持久存储
- **但会话状态不是检查点化的**：Agent 崩溃后无法从中间状态恢复
- 会话转录 ≠ 执行检查点 —— 转录是日志，不能用于精确恢复执行状态
- 只有 Managed Agents 提供了会话持久化（但有额外成本）

**可观测性** ⚠️ 良好（需配置）
- OpenTelemetry 支持（通过环境变量启用）
- `ResultMessage` 包含执行统计（成本、轮次）
- `StreamEvent` 提供实时事件流
- 但不包含 LangSmith 式的全链路可视化
- 自定义审计日志需通过 PostToolUse Hooks 实现
- **提示词文本和工具输入默认不包含在 Trace 中**（需显式 opt-in）

### 3.4 部署方式

**纯自托管**（SDK 本身）:
- 需自行构建 HTTP/WebSocket/SSE 服务器
- 需自行管理认证、多租户、会话路由
- 三种部署层级：
  - **Tier 1 - Docker**: 开发循环、内部工具、单租户
  - **Tier 2 - Modal**: 托管 Serverless、自动缩容至零
  - **Tier 3 - Kubernetes**: 完全控制、多租户、受监管环境
- 每 Agent 约需 1 GiB RAM / 5 GiB 磁盘 / 1 CPU
- 推荐会话模式：临时式 / 持久式 / 多 Agent 容器 / 混合式

**Managed Agents**（独立产品，公测中）:
- 2026 年推出的云托管方案
- Anthropic 管理沙箱、认证、工具执行
- 支持长时间运行会话、多 Agent 协调
- 定价：标准 Token 费率 + $0.08/会话-小时
- **SDK 代码无法直接部署到 Managed Agents**

### 3.5 生态与集成

- **模型**: Claude 专属（Anthropic API、Bedrock、Vertex、Azure）
- **微软 Agent Framework 集成** (2026年1月): 实现 `BaseAgent` 接口，可与其他提供商 Agent 混用
- **GitHub Actions**: `anthropics/claude-code-action`
- **MCP 生态**: 丰富的社区 MCP Server
- **grip-ai**: 开源自托管平台，双引擎架构（Claude SDK + LiteLLM fallback 支持 15+ 提供商）

### 3.6 优缺点总结

| 优点 | 缺点 |
|------|------|
| Claude 模型最优性能（原生 Prompt Caching、Extended Thinking） | 模型供应商锁定（仅 Claude） |
| 细粒度权限和 Hooks 安全机制成熟 | 多租户/数据隔离需大量自建 |
| SDK 轻量，启动简单 | 缺乏内置 RAG 管道 |
| Skill、MCP 生态完善 | 缺乏框架级检查点/故障恢复 |
| 微软 Agent Framework 跨供应商互操作 | 无托管部署选项（需自行运维） |
| 丰富的社区案例和 Cookbook | 可观测性需自行搭建 |
| Managed Agents 提供免运维方案 | 子进程架构增加运维复杂度 |

---

## 4. 逐项对比分析

### 4.1 通用 Agent 能力对比

| 能力 | LangChain Deep Agents | Claude Agent SDK | 差异分析 |
|------|----------------------|------------------|---------|
| **工具调用** | ✅ Middleware 注入，支持沙箱代码执行 | ✅ 14+ 内置工具，细粒度权限控制 | DA 更灵活；SDK 权限更精细 |
| **多轮对话** | ✅ Thread + 自动摘要 | ✅ Session 管理 + Compaction | 相当 |
| **任务编排** | ✅ LangGraph DAG + 并行执行 | ⚠️ Agent 自主规划 + Workflow 工具 | DA 显式编排；SDK 依赖 Agent 自主 |
| **多 Agent** | ✅ 3 种子 Agent + 嵌套 + 异构模型 | ✅ 3 种子 Agent + 嵌套 + Workflow | DA 更灵活（异构模型）；SDK 规模化更好 |
| **Skill** | ✅ SKILL.md + 渐进式披露 | ✅ SKILL.md + 渐进式披露 | 相当（都源自同一标准） |
| **MCP** | ✅ Client/Server 双向 | ✅ Client + 每 Agent 子集配置 | DA 可对外暴露 MCP；SDK 仅消费 |
| **知识库 RAG** | ✅ Store + pgvector，内置语义搜索 | ⚠️ 需通过 MCP Server 自建 | **DA 明显胜出** |

### 4.2 企业级特性对比

| 能力 | LangChain Deep Agents | Claude Agent SDK | 差异分析 |
|------|----------------------|------------------|---------|
| **数据隔离** | ✅ 内置多租户 + RBAC | ⚠️ 需容器化 + 大量自建 | **DA 明显胜出** |
| **数据安全** | ✅ PII Middleware + 路径防护 + Sandbox | ✅ 多层权限 + 凭证代理 + Hooks | SDK 更精细 |
| **安全围栏** | ✅ 多层 Guardrails + Middleware 链 | ✅ 14+ Hooks + 工具级 deny/allow | SDK 更成熟 |
| **人机协同** | ✅ interrupt + 4 种决策 + 检查点恢复 | ⚠️ needs_approval + Permission Hooks | **DA 明显胜出** |
| **长期记忆** | ✅ Store + 语义搜索 + 三级作用域 | ⚠️ 需自建（MCP/外部服务） | **DA 明显胜出** |
| **短?记忆** | ✅ Thread 检查点 | ✅ Session 转录 | 相当 |
| **断点持久化** | ✅ Durable Execution + 检查点 + 时间旅行 | ⚠️ 转录 ≠ 检查点，无故障恢复 | **DA 明显胜出** |
| **可观测性** | ✅ LangSmith 全链路 + 可视化 + Online Eval | ⚠️ OTel + 自建审计 | **DA 明显胜出** |

### 4.3 架构与运维对比

| 维度 | LangChain Deep Agents | Claude Agent SDK |
|------|----------------------|------------------|
| **进程模型** | Python 进程内状态图（透明、可检查） | CLI 子进程（灰盒） |
| **部署模式** | 托管 (LangSmith) + 自托管 (Docker/K8s) | 纯自托管（需自行构建服务层） |
| **BS 架构适配** | 自带 Agent Server（30+ 端点） | 需自行构建 HTTP/SSE 层 |
| **多用户并发** | 内置 Thread 隔离 + 水平扩展 | 需自建会话路由 + Sandbox 管理 |
| **开箱即用度** | 高（部署即得完整 API） | 低（需大量基础设施搭建） |
| **供应商锁定** | 无（100+ 模型提供商） | 有（仅 Claude 模型） |
| **模型优化深度** | 中等（通用接口） | 极致（Prompt Caching、Extended Thinking、模型分层） |
| **学习曲线** | 较陡（LangGraph 概念体系） | 中等（Claude Code 概念即可） |

---

## 5. 综合评分矩阵

| 评估维度 | 权重 | LangChain Deep Agents | Claude Agent SDK |
|----------|------|----------------------|------------------|
| 工具调用 | 10% | 8 | 9 |
| 多轮对话 | 8% | 9 | 8 |
| 任务编排 | 10% | 9 | 7 |
| 多 Agent 协作 | 10% | 9 | 8 |
| Skill 系统 | 5% | 8 | 8 |
| MCP 集成 | 8% | 9 | 8 |
| 知识库 RAG | 10% | 9 | 5 |
| 数据隔离 | 8% | 9 | 4 |
| 数据安全 | 8% | 7 | 9 |
| 安全围栏 | 5% | 7 | 9 |
| 人机协同 | 8% | 9 | 5 |
| 长期记忆 | 5% | 9 | 4 |
| 断点持久化 | 5% | 9 | 3 |
| 可观测性 | 8% | 9 | 5 |
| 部署运维 | 8% | 8 | 5 |
| 生态开放性 | 5% | 9 | 5 |
| **加权总分** | | **8.60** | **6.43** |

> 权重分配说明：基于企业级 BS 平台需求，**知识库检索、多 Agent 协作、任务编排、工具调用**是核心功能（权重 10%）；**数据隔离、可观测性、人机协同、部署运维**是企业级刚需（权重 8%）。

---

## 6. 选型结论与建议

### 6.1 推荐方案：LangChain Deep Agents

**推荐理由**：

1. **企业级特性内置化程度高**：多租户数据隔离、人机协同审批、断点持久化、长期记忆是可用的框架原语，而非需要从头构建的基础设施。这对于需要快速交付的企业平台至关重要。

2. **BS 架构适配成本低**：Deep Agents 通过 `langgraph build` 直接产出自带 30+ REST/SSE 端点的 Docker 镜像，包括流式传输、线程管理、认证、Webhook，大幅缩短从 Agent 逻辑到可调用 API 的距离。对比 Claude Agent SDK 需要从零搭建整个 HTTP 服务层。

3. **模型无关性降低战略风险**：企业 Agent 平台需要根据场景选择最优模型（成本/性能/延迟），Deep Agents 支持 100+ 提供商，避免被单一供应商锁定。同时可以在不同子 Agent 中使用不同模型。

4. **记忆和持久化是第一等公民**：LangGraph 的 Durable Execution + Store 架构使得长短期记忆、会话恢复、时间旅行调试成为框架的有机部分，而非事后补丁。

5. **可观测性开箱即用**：LangSmith 的全链路追踪、Online Eval、可视化调试对企业级平台的稳定运维和持续优化是必备能力。Claude SDK 的 OTel + 自建方案需要大量额外投入。

6. **已有企业落地验证**：Rippling（6 个月从 0 到全产品线 AI Native）、OpenSWE（开源自主编程 Agent）、LangChain 内部 GTM Agent（250% 线索转化提升）均基于 Deep Agents 构建。

### 6.2 Claude Agent SDK 的适用场景

Claude Agent SDK 在以下场景仍然是最优选择：

- **内部开发工具/个人 Agent**：如 IDE 插件、CLI 工具、代码审查 Agent
- **Claude 模型深度依赖**：需要 Prompt Caching、Extended Thinking 等独占特性达到最优性价比
- **安全合规优先**：14+ Hooks 提供无与伦比的细粒度审计能力
- **已深度使用 Claude Code 的团队**：复用现有 Skill、MCP 配置

### 6.3 混合策略的可能性

如果团队对 Claude 模型有不可替代的需求，可以考虑 **混合架构**：

```
┌──────────────────────────────────────────┐
│         企业 Agent 平台 (BS)              │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │   LangChain Deep Agents (主框架)    │  │
│  │   · 多租户 · 编排 · RAG · 记忆      │  │
│  │   · 人机协同 · 检查点 · 可观测性    │  │
│  └──────────────┬─────────────────────┘  │
│                 │                         │
│  ┌──────────────▼─────────────────────┐  │
│  │   模型路由层 (LangChain Model)      │  │
│  │   Claude / GPT / Gemini / ...      │  │
│  └────────────────────────────────────┘  │
│                 │                         │
│  ┌──────────────▼─────────────────────┐  │
│  │   可选: Claude Agent SDK 嵌入式      │  │
│  │   特定子 Agent (需要 Claude 优化)    │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

但这会显著增加架构复杂度和维护成本，**建议先在 Deep Agents 中使用 Claude 作为主要模型**，保留后续引入 SDK 的空间。

---

## 7. 推荐架构蓝图

基于 LangChain Deep Agents 的企业 Agent 平台架构：

```
┌──────────────────────────────────────────────────────────────────┐
│                        前端层 (Browser)                           │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Chat UI │ Agent Manager │ Knowledge Base │ Admin Console    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP/SSE (Agent Server Endpoints)
┌──────────────────────────────▼───────────────────────────────────┐
│                      网关层 (Nginx/Kong)                          │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  认证 (OAuth2/OIDC) │ 速率限制 │ 路由 │ 审计日志             │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────┐
│                 Agent 服务层 (Deep Agents Server)                  │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │ │
│  │  │ Agent A  │  │ Agent B  │  │ Agent C  │  ... (水平扩展)    │ │
│  │  │ Thread   │  │ Thread   │  │ Thread   │                   │ │
│  │  └──────────┘  └──────────┘  └──────────┘                   │ │
│  │       │              │              │                         │ │
│  │  ┌────┴──────────────┴──────────────┴─────────────────────┐  │ │
│  │  │              LangGraph Runtime                          │  │ │
│  │  │  · Checkpoint  · Interrupt (HITL)  · Streaming        │  │ │
│  │  │  · Middleware Chain  · Skills  · Sub-agents            │  │ │
│  │  └────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                      能力中间件层                                  │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Guardrails│ │ PII       │ │ Memory   │ │ Human-in-the-    │  │
│  │ Middleware│ │ Detector  │ │ Middleware│ │ Loop Middleware  │  │
│  └───────────┘ └───────────┘ └──────────┘ └──────────────────┘  │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│                      数据与基础设施层                               │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ PostgreSQL│ │ pgvector  │ │ MCP      │ │ LangSmith        │  │
│  │ (检查点,   │ │ (向量库)  │ │ Servers  │ │ (可观测性)        │  │
│  │  Store,    │ │           │ │          │ │                  │  │
│  │  记忆)     │ │           │ │          │ │                  │  │
│  └───────────┘ └───────────┘ └──────────┘ └──────────────────┘  │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Redis     │ │ Object    │ │ LLM      │ │ Sandbox          │  │
│  │ (缓存,     │ │ Storage   │ │ Provider │ │ Runtime          │  │
│  │  Session)  │ │ (S3/MinIO)│ │ Gateway  │ │ (Docker/K8s)     │  │
│  └───────────┘ └───────────┘ └──────────┘ └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 关键技术选型建议

| 组件 | 推荐方案 | 说明 |
|------|----------|------|
| **Agent 框架** | LangChain Deep Agents | 基于本报告选型结论 |
| **LLM 网关** | 多模型 (Claude + GPT + 国产模型) | Deep Agents 模型无关，按场景路由 |
| **对话状态** | LangGraph Checkpoint (PostgreSQL) | Durable Execution + 时间旅行 |
| **长期记忆** | LangGraph Store (PostgreSQL + pgvector) | 语义搜索 + 三级作用域 |
| **向量数据库** | pgvector | 与 PostgreSQL 统一运维 |
| **知识库** | StoreBackend + CompositeBackend | 以虚拟文件系统方式暴露给 Agent |
| **安全围栏** | Middleware Chain (PII + Guardrails + HITL) | 多层可堆叠 |
| **人机协同** | LangGraph interrupt + 自定义审批 UI | 4 种决策类型 |
| **可观测性** | LangSmith / OpenTelemetry | 全链路追踪 + Online Eval |
| **前端** | React/Vue + SSE Streaming | 流式对话体验 |
| **容器编排** | Kubernetes | 水平扩展、滚动更新、自愈 |
| **MCP 集成** | Deep Agents 内置 MCP Client/Server | 双向 MCP 支持 |

---

## 8. 风险与注意事项

### 8.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LangChain 版本迭代快，API 不稳定 | 升级成本 | 锁定 minor 版本，建立集成测试 |
| LangSmith 托管服务依赖 | 供应商锁定 | 保持自托管部署能力，使用 OpenTelemetry 作为备份观测方案 |
| 大规模并发下的 LangGraph 性能 | 用户体验 | 在 K8s 上水平扩展 Agent 实例，Redis 会话路由 |
| Claude Agent SDK 作为备选的知识储备 | 架构灵活性 | 保留混合架构接口，关键子 Agent 可切换实现 |

### 8.2 实施建议

1. **分阶段交付**：
   - Phase 1: 单 Agent + 基础工具调用 + RAG 知识库
   - Phase 2: 多 Agent 协作 + 人机协同
   - Phase 3: 多租户 + 安全围栏 + 可观测性
   - Phase 4: MCP 生态 + 自定义 Skill 市场

2. **关键基础设施建设先行**：PostgreSQL（含 pgvector）是所有状态管理的基础，应最先就绪。

3. **模型策略**：初期可以主要使用 Claude（通过 Anthropic API），同时保持 LangChain 的模型无关接口，后续根据成本/性能按需引入 GPT、Gemini 或国产模型。

4. **安全围栏逐步完善**：先用低成本的确定性规则（正则、关键词）覆盖高频风险，再逐步引入 LLM 评估围栏。

---

## 附录：参考资源

- [LangChain Deep Agents Overview](https://docs.langchain.com/oss/javascript/deepagents/overview)
- [LangChain Deep Agents vs Claude Agent SDK Comparison](https://docs.langchain.com/oss/javascript/deepagents/comparison)
- [Claude Agent SDK Hosting Guide](https://code.claude.com/docs/en/agent-sdk/hosting)
- [LangGraph Durable Execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)
- [NVIDIA NeMoClaw Deep Agents Blueprint](https://www.langchain.com/blog/nvidia-enterprise)
- [Rippling AI on Deep Agents](https://www.langchain.com/blog/how-rippling-went-ai-native-across-every-product-in-6-months-with-deep-agents-and-langsmith)
- [Claude Managed Agents](https://claude.com/blog/claude-managed-agents)
- [Claude Agent SDK + Microsoft Agent Framework](https://devblogs.microsoft.com/agent-framework/build-ai-agents-with-claude-agent-sdk-and-microsoft-agent-framework/)
