# EAP — 企业 Agent 平台

> 多租户 AI Agent 平台 · BS 架构 · 内网部署
>
> [:us: English](README.en.md)

EAP（Enterprise Agent Platform）是一个面向企业的多租户 AI 智能体平台。用户在平台上创建智能体（Agent），为其配置模型通道、工具、知识库、技能与子智能体，通过浏览器进行流式对话；平台提供 RBAC 权限、租户数据隔离、安全围栏、容器沙箱执行、人机协同审批（HITL）与全链路调用监控。

## 核心特性

- **多租户隔离**：所有 DB 查询按 `tenant_id` 过滤；对话线程 ID 形如 `{tenant_slug}:{user_id}:{uuid}`；执行沙箱按租户/用户/线程目录隔离
- **RBAC 权限**：用户 → 角色 → 权限（`resource:action` 编码）；JWT + Redis 会话，支持权限即时撤销与强制下线
- **流式对话**：SSE 逐 token 输出，工具调用全程可视化（中文别名、参数、结果）
- **模型通道**：DeepSeek / OpenAI / Anthropic / LM Studio 统一接入；支持平台级与智能体级绑定，API key 运行时解析
- **智能体能力**：内置工具（计算器、时间、联网搜索、知识库检索、记忆存取）+ deepagents 默认工具（任务规划、文件读写、grep/glob）+ MCP 外部工具
- **知识库与 RAG**：文档上传解析（PDF / DOCX / TXT），中英文分词检索，集合级授权
- **双层记忆**：全局记忆（DB 持久化，高重要性条目自动注入系统提示词）+ 会话记忆文件
- **Skills 与子智能体**：prompt 型技能渐进披露；agent 型技能 / 子智能体具备独立上下文，可绑定独立模型
- **安全执行后端**：`local`（无 shell 文件沙箱）/ `container`（Docker 一次性容器：禁网、限内存、`--cap-drop ALL`，fail-closed）
- **人机协同（HITL）**：写文件 / 编辑 / shell 执行可配置人工审批；聊天页内嵌审批卡，批准 / 拒绝 / 编辑后批准，自动断点续流
- **安全围栏**：PII 脱敏（Presidio）+ 内容安全双重检查，输入输出双侧防护
- **全链路监控**：trace、token 用量与成本记录（LangSmith 兼容 + OpenTelemetry）

## 系统架构

```
浏览器 ──▶ Nginx(:80) ── /eap/* ────────▶ React SPA 静态资源
              │
              └── /eap/api/* ──▶ Gunicorn(:5003) ──▶ Flask ──▶ deepagents 编排核心
                                                             │
        ┌────────────────────────────────────────────────────┼──────────────────────────┐
        │                                                    │                          │
  PostgreSQL 16 + pgvector                          Redis 7（会话 / 权限缓存）   Docker（容器沙箱）
  （业务数据 / 知识库向量 / 检查点）                    （仅本机）               --network none 一次性容器
```

- **前端**：React 18 + Ant Design 5 + Vite，`/eap` 前缀部署，SSE 流式渲染
- **后端**：Flask 3 + deepagents（LangGraph），双流模式（`messages` 逐 token + `updates` 完整工具参数）
- **编排核心**：DeepAgentFactory 按 Agent 配置组装 deepagents 图（模型 / 工具 / 技能 / 子智能体 / 执行后端），编译图 LRU 缓存；PostgresSaver 检查点持久化，支持断点续聊
- **中断恢复**：LangGraph interrupt → 审批落库 → 批准后 resume 继续流式输出

## 目录结构

```
backend/             Flask 后端
  app/api/v1/        REST + SSE 接口（chat / agent / workflow / knowledge …）
  app/core/agent/    deepagents 编排核心（factory / orchestrator / backends / tools）
  app/core/guardrails/  安全围栏（PII 脱敏 + 内容安全）
  app/models/        数据模型
frontend/            React 前端（Vite + AntD + zustand）
scripts/             运维与测试脚本（eap_full_test.sh 回归套件等）
docs/superpowers/    设计规格与实施计划
skills/              平台级技能目录
mcp_servers/         MCP 服务配置
docker-compose.yml   本地基础设施（PostgreSQL / Redis）
```

## 快速开始

### 前置条件

- Python 3.11+、Node.js 18+
- PostgreSQL 16 + pgvector、Redis 7（本地可用 `docker-compose.yml` 拉起，或复用开发服务器实例）

### 安装与启动

```bash
make install        # 安装 Python + Node 依赖
make dev-backend    # Flask 开发服务器 :5000（需可访问 PG/Redis）
make dev-frontend   # Vite 开发服务器 :3000（/eap → :5000 代理）
```

首次启动自动初始化：默认租户、admin / viewer 用户、预置角色与权限、模型通道种子数据。

访问 http://localhost:3000/eap

### 配置

复制 `.env.example` 为 `backend/.env`，配置数据库 / Redis 连接与模型 API key。

## 部署

生产环境：Nginx + Gunicorn + PostgreSQL + Redis + Docker，内网服务器部署。

```bash
make deploy            # 构建前端 + 同步后端 + 重启（完整部署）
make deploy-backend    # 仅同步后端
make deploy-frontend   # 仅构建同步前端
make server-info       # 服务器状态 / 端口 / 磁盘检查
```

## 测试

```bash
bash scripts/eap_full_test.sh
```

部署级集成回归套件：93 项检查，覆盖认证 / RBAC / 智能体 CRUD / 工具 / 记忆 / 技能 / 子智能体 / 知识库 RAG / 安全围栏 / 人机协同 / 监控链路。

## 设计文档

- 编排核心 deepagents 化设计：[docs/superpowers/specs/2026-08-30-deepagents-orchestration-design.md](docs/superpowers/specs/2026-08-30-deepagents-orchestration-design.md)
- 实施计划：[docs/superpowers/plans/2026-08-30-deepagents-orchestration.md](docs/superpowers/plans/2026-08-30-deepagents-orchestration.md)
