# 企业级 Agent 平台 (EAP) — 功能文档

> **版本**: v2.0 | **日期**: 2026-07-25 | **基于**: Phase 1-5 全量规划（Phase 1 已实现，Phase 2-5 设计中）

---

## 目录

1. [系统概述](#1-系统概述)
2. [F-01 用户认证模块](#f-01-用户认证模块)
3. [F-02 RBAC 权限模块](#f-02-rbac-权限模块)
4. [F-03 对话模块](#f-03-对话模块)
5. [F-04 Agent 管理模块](#f-04-agent-管理模块)
6. [F-05 模型配置模块](#f-05-模型配置模块)
7. [F-06 管理后台模块](#f-06-管理后台模块)
8. [F-07 安全与合规模块](#f-07-安全与合规模块)
9. [F-08 Skill 管理模块](#f-08-skill-管理模块)
10. [F-09 MCP Server 管理模块](#f-09-mcp-server-管理模块)
11. [F-10 知识库模块 (Phase 2)](#f-10-知识库模块-phase-2)
12. [F-11 文档管理模块 (Phase 2)](#f-11-文档管理模块-phase-2)
13. [F-12 RAG Agent 模块 (Phase 2)](#f-12-rag-agent-模块-phase-2)
14. [F-13 多 Agent 编排模块 (Phase 3)](#f-13-多-agent-编排模块-phase-3)
15. [F-14 安全围栏模块 (Phase 4)](#f-14-安全围栏模块-phase-4)
16. [F-15 人机协同模块 (Phase 4)](#f-15-人机协同模块-phase-4)
17. [F-16 长期记忆模块 (Phase 4)](#f-16-长期记忆模块-phase-4)
18. [F-17 可观测性模块 (Phase 5)](#f-17-可观测性模块-phase-5)
19. [F-18 成本监控模块 (Phase 5)](#f-18-成本监控模块-phase-5)
20. [F-19 系统运维模块 (Phase 5)](#f-19-系统运维模块-phase-5)
21. [页面路由映射](#页面路由映射)
22. [阶段交付矩阵](#阶段交付矩阵)

---

## 1. 系统概述

EAP 是基于 LangChain Deep Agents + Flask + React 构建的企业级 Agent 平台（BS 架构），支持多租户、多用户并发。规划 5 个阶段交付：Phase 1（基础设施+对话）已实现，Phase 2-5（知识库/多Agent/安全围栏/可观测性）为后续阶段。本文档覆盖全部 5 个阶段的完整功能规格。

### 1.1 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design 5 + Zustand |
| 后端 | Flask 3.x + LangGraph + LangChain |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| LLM | DeepSeek V4 Pro（可扩展多模型） |
| 部署 | Nginx + Gunicorn + Systemd |

### 1.2 访问地址

- **生产环境**: `http://192.168.1.51`
- **默认管理员**: `admin@example.com / CHANGE_ME`
- **默认查看者**: `viewer@example.com / CHANGE_ME`

---

## 2. F-01 用户认证模块

### 2.1 功能概述

基于 **JWT + Redis Session** 的认证体系。JWT 仅携带 `sub`（用户ID）和 `jti`（Token唯一ID），角色、权限、租户等业务信息存储在 Redis 中。

### 2.2 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-01-01 | 用户登录 | 邮箱+密码登录，返回 JWT + 用户信息 |
| F-01-02 | 用户注册 | 创建租户+管理员用户，自动分配 TenantAdmin 角色 |
| F-01-03 | Token 刷新 | 使用 refresh_token 换取新 access_token（jti 轮换） |
| F-01-04 | 用户登出 | 删除 Redis Session，JWT 即时失效 |
| F-01-05 | 当前用户信息 | 从 Redis 读取当前登录用户的完整信息 |
| F-01-06 | 强制下线 | 管理员可删除指定用户的所有 Redis Session |
| F-01-07 | 权限即时生效 | 修改角色/权限后刷新对应用户所有活跃 Session |
| F-01-08 | Token 自动过期 | JWT 有效期 2 小时，refresh_token 30 天 |

### 2.3 API 端点

```
POST   /api/v1/auth/login       # 登录
POST   /api/v1/auth/register    # 注册
POST   /api/v1/auth/refresh     # 刷新 Token
POST   /api/v1/auth/logout      # 登出
GET    /api/v1/auth/me          # 当前用户信息
```

### 2.4 登录流程

```
[前端] → POST /auth/login {email, password}
  → [后端] 验证密码 → 签发 JWT(sub+jti) → 写入 Redis Session
  → [前端] 存储 access_token → 跳转到 /chat
  → [每次请求] Authorization: Bearer {token}
    → [中间件] 验证 JWT → Redis 读取 Session → 注入 g 对象
```

### 2.5 前端页面

- **登录页** (`/login`): 登录表单 + 注册表单（Tab 切换），默认账号提示
- **登录保护** (`ProtectedRoute`): 未登录用户自动跳转到 `/login`

---

## 3. F-02 RBAC 权限模块

### 3.1 功能概述

基于 **User → Role → Permission** 的三层权限模型。权限点为 `resource:action` 格式（如 `agent:create`）。权限信息存储在 Redis Session 中，修改后即时生效。

### 3.2 预置角色

| 角色 | 权限范围 | 说明 |
|------|---------|------|
| SuperAdmin | `*:*` 全部权限 | 系统超级管理员 |
| TenantAdmin | `user:*`, `agent:*`, `knowledge:*`, `admin:audit`, `admin:settings`, `approval:approve` | 租户管理员 |
| Developer | `agent:create/update/execute/read`, `knowledge:*`, `skill:*`, `mcp:*` | 开发者 |
| Viewer | `agent:read`, `agent:execute`, `knowledge:read`, `skill:read`, `mcp:read` | 只读查看者 |

### 3.3 预置权限点（23项）

| 权限码 | 说明 |
|--------|------|
| `*:*` | 超级管理员 |
| `user:create/read/update/delete` | 用户 CRUD |
| `agent:create/read/update/delete/execute` | Agent 管理 |
| `knowledge:create/read/update/delete` | 知识库管理 |
| `skill:read/manage` | Skill 管理 |
| `mcp:read/manage` | MCP 管理 |
| `admin:access/audit/settings` | 管理后台 |
| `approval:approve` | 审批操作 |

### 3.4 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-02-01 | 角色管理 | 查看/创建/编辑/删除角色 |
| F-02-02 | 用户管理 | 创建/编辑/删除用户，分配角色 |
| F-02-03 | 权限拦截 | API 级别 `require_permission(codename)` 装饰器 |
| F-02-04 | 前端权限门控 | `PermissionGate` 组件：无权限时隐藏菜单/按钮 |
| F-02-05 | 权限即时生效 | 修改用户角色后自动刷新 Redis Session |

### 3.5 API 端点

```
GET    /api/v1/admin/users          # 用户列表
POST   /api/v1/admin/users          # 创建用户
PUT    /api/v1/admin/users/:id      # 更新用户（含角色分配）
DELETE /api/v1/admin/users/:id      # 删除用户（同时强制下线）
GET    /api/v1/admin/roles          # 角色列表
POST   /api/v1/admin/roles          # 创建自定义角色
```

---

## 4. F-03 对话模块

### 4.1 功能概述

基于 LangGraph + DeepSeek V4 Pro 的 AI 对话，支持 SSE 流式输出、多轮上下文保持、工具调用（含参数展示）、模型选择。

### 4.2 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-03-01 | 流式对话 | SSE 实时推送 token，前端 Markdown 渲染 + 光标闪烁 |
| F-03-02 | 多轮对话 | LangGraph checkpoint 保持对话上下文 |
| F-03-03 | 工具调用 | AI 可调用内置工具（calculator 等），展示参数和结果 |
| F-03-04 | 模型选择 | 前端下拉框切换可用模型 |
| F-03-05 | 停止生成 | 流式输出过程中可随时中止 |
| F-03-06 | 对话线程 | 支持创建/查看/删除对话线程 |
| F-03-07 | Enter 发送 | Enter 发送消息，Shift+Enter 换行 |

### 4.3 SSE 事件类型

| type | 描述 | 触发时机 |
|------|------|---------|
| `token` | 文本内容片段 | LLM 流式输出每个 token |
| `tool_start` | 工具调用开始（含完整参数） | Agent 决定调用工具 |
| `tool_end` | 工具调用完成（含输出） | 工具执行返回 |
| `error` | 错误信息 | 任何异常 |
| `done` | 对话完成 | Agent 执行结束 |

### 4.4 API 端点

```
POST   /api/v1/chat/stream            # SSE 流式对话（支持 model_provider_id 参数）
GET    /api/v1/chat/threads           # 当前用户对话线程列表
GET    /api/v1/chat/threads/:id       # 线程详情（消息历史）
DELETE /api/v1/chat/threads/:id       # 删除线程
```

### 4.5 前端页面

- **对话主页** (`/chat`, `/chat/:threadId`): 
  - 顶部模型选择器
  - 消息列表（用户/AI/工具调用/错误）  
  - 底部输入框 + 发送/停止按钮
  - 流式光标动画
  - Markdown 代码块语法高亮

---

## 5. F-04 Agent 管理模块

### 5.1 功能概述

管理员可以创建、编辑、删除 Agent 配置。Agent 配置包括模型选择、系统提示词、工具集、权限模式等。

### 5.2 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-04-01 | Agent 列表 | 分页表格展示所有 Agent |
| F-04-02 | 创建 Agent | 配置名称/模型/提示词/工具/权限模式 |
| F-04-03 | 编辑 Agent | 修改 Agent 配置参数 |
| F-04-04 | 删除 Agent | 确认后删除 Agent 配置 |
| F-04-05 | 启用/禁用 | 切换 Agent 的 is_active 状态 |

### 5.3 Agent 配置字段

| 字段 | 类型 | 说明 |
|------|------|------|
| name | String | Agent 名称（租户内唯一） |
| model | String | 使用模型（如 deepseek-v4-pro） |
| system_prompt | Text | 自定义系统提示词 |
| tools_config | JSON Array | 启用的工具列表 |
| skills | JSON Array | 绑定的 Skill |
| mcp_servers | JSON Array | 绑定的 MCP Server |
| permission_mode | Enum | default / acceptEdits / dontAsk |
| max_turns | Integer | 最大对话轮次（1-100） |
| is_active | Boolean | 是否启用 |

### 5.4 API 端点

```
GET    /api/v1/agents
POST   /api/v1/agents
GET    /api/v1/agents/:id
PUT    /api/v1/agents/:id
DELETE /api/v1/agents/:id
```

---

## 6. F-05 模型配置模块

### 6.1 功能概述

管理员可以为租户动态配置 LLM 接入信息（供应商、API Key、模型名），无需重启服务。配置后用户在聊天页下拉框中选择。

### 6.2 支持的供应商

| 供应商 | 默认 API 地址 | 说明 |
|--------|-------------|------|
| deepseek | `https://api.deepseek.com/v1` | 默认供应商 |
| anthropic | 默认 | Claude 系列 |
| openai | 默认 | GPT 系列 |

### 6.3 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-05-01 | 模型列表 | 查看所有已配置的模型（含脱敏 Key） |
| F-05-02 | 添加模型 | 配置名称/供应商/Key/模型名/API 地址 |
| F-05-03 | 编辑模型 | 修改模型配置 |
| F-05-04 | 删除模型 | 删除模型配置 |
| F-05-05 | 设为默认 | 设置某个模型为默认（先取消其他默认） |
| F-05-06 | 启用/禁用 | 切换 is_active，禁用的模型不出现在选择器中 |
| F-05-07 | Key 脱敏 | 前端仅显示 `sk-ant****xxxx` 格式 |
| F-05-08 | 可用模型列表 | 公开接口，供聊天页下拉框使用 |

### 6.4 API 端点

```
GET    /api/v1/admin/models           # 模型列表（含脱敏 Key）
POST   /api/v1/admin/models           # 添加模型
PUT    /api/v1/admin/models/:id       # 更新模型
DELETE /api/v1/admin/models/:id       # 删除模型
GET    /api/v1/models/available       # 公开：可用模型列表（聊天页使用）
```

### 6.5 模型选择流程

```
[管理后台] 添加模型 → 数据库 model_providers 表
[聊天页] GET /api/v1/models/available → 渲染下拉框
[用户选择] → POST /chat/stream {model_provider_id: N}
[后端] _resolve_provider_config → 读取 DB 配置 → 构建 LLM
```

---

## 7. F-06 管理后台模块

### 7.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-06-01 | 用户管理页 | 查看/创建/编辑/删除用户 |
| F-06-02 | 角色管理 | 查看角色列表，创建自定义角色 |
| F-06-03 | 模型配置页 | 模型供应商 CRUD |
| F-06-04 | 审计日志 | 查看/筛选/分页审计日志 |
| F-06-05 | 健康检查 | 数据库/Redis/LLM 连通性检测 |

### 7.2 审计日志

所有关键操作自动记录审计日志，存储在 `audit_logs` 表：

| action | 触发操作 |
|--------|---------|
| `user:login` | 用户登录 |
| `user:login_failed` | 登录失败 |
| `user:logout` | 用户登出 |
| `agent:execute` | Agent 对话执行 |
| `admin:user_create` | 创建用户 |
| `admin:model_create` | 添加模型配置 |
| `chat:delete_thread` | 删除对话线程 |

---

## 8. F-07 安全与合规模块

### 8.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-07-01 | JWT 无状态验证 | 签名验证 + 过期检查 |
| F-07-02 | Redis Session 管理 | 会话创建/刷新/销毁/批量销毁 |
| F-07-03 | 多租户数据隔离 | Thread ID 含 `tenant_slug`、DB 查询带 `tenant_id` 过滤 |
| F-07-04 | 请求级用户上下文 | `g.user_id / g.tenant_slug / g.permissions` |
| F-07-05 | 权限变更即时生效 | 修改角色后刷新所有活跃 Redis Session |
| F-07-06 | Token 强制失效 | 删除 Redis Session 后 JWT 立即失效（返回 401） |
| F-07-07 | API 级别权限检查 | `require_permission(codename)` 装饰器 |
| F-07-08 | CORS 白名单 | 仅允许配置的 Origin |

---

## 9. F-08 Skill 管理模块

### 9.1 功能概述

用户可通过上传 ZIP 压缩包创建 Skill，包内必须包含 `SKILL.md` 文件（YAML frontmatter + Markdown 指令）。系统自动解析元数据、持久化文件并存储完整配置。

### 9.2 Skill ZIP 包结构

```
my_skill/
├── SKILL.md        ← 必须，YAML frontmatter 定义 name/description/version/tools/tags
├── scripts/        ← 可选，可执行脚本
└── prompts/        ← 可选，提示词模板
```

**SKILL.md frontmatter 示例**：

```yaml
---
name: web_search
description: 互联网搜索技能
version: 1.0.0
author: EAP Team
tools: [web_search, fetch_webpage]
tags: [search, research]
trigger_keywords: [搜索, 查找]
---
# Web Search Skill
...
```

### 9.3 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-08-01 | Skill 列表 | 查看租户下所有 Skill（名称/版本/标签/工具/状态） |
| F-08-02 | 上传 Skill | ZIP 拖拽上传，自动解析 SKILL.md 并持久化 |
| F-08-03 | Skill 详情 | 查看完整 SKILL.md 内容和元数据 |
| F-08-04 | 启用/禁用 | 切换 is_active，禁用的 Skill 不被 Agent 加载 |
| F-08-05 | 删除 Skill | 删除记录 + 清理文件 |
| F-08-06 | 文件去重 | SHA256 校验，已存在的 Skill 拒绝重复上传 |
| F-08-07 | 重名校验 | 租户内 Skill 名称唯一 |

### 9.4 API 端点

```
GET    /api/v1/skills                  # Skill 列表
GET    /api/v1/skills/:id              # Skill 详情（含 SKILL.md 全文）
POST   /api/v1/skills/upload           # 上传 ZIP（multipart/form-data）
PUT    /api/v1/skills/:id              # 更新元数据
DELETE /api/v1/skills/:id              # 删除 Skill
POST   /api/v1/skills/:id/toggle       # 启用/禁用
```

---

## 10. F-09 MCP Server 管理模块

### 10.1 功能概述

用户可手动配置 **stdio**（命令行进程）和 **SSE**（远程服务）两种类型的 MCP Server。配置信息存储在服务端 PostgreSQL 中，支持连接测试。

### 10.2 两种传输模式

| 模式 | 关键字段 | 适用场景 |
|------|---------|---------|
| **STDIO** | `command`, `args`, `env` | 本地命令行 MCP 服务器（如 npx @mcp/server-filesystem） |
| **SSE** | `sse_url`, `sse_headers` | 远程 HTTP SSE 服务（如 http://host:8080/sse） |

### 10.3 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-09-01 | Server 列表 | 查看所有 MCP Server（名称/类型/命令URL/状态） |
| F-09-02 | 创建 Server | 按类型动态表单配置 stdio 或 SSE 连接 |
| F-09-03 | 编辑 Server | 修改配置参数 |
| F-09-04 | 删除 Server | 删除 MCP Server 配置 |
| F-09-05 | 连接测试 | 测试 stdio 命令执行或 SSE 端点可达性 |
| F-09-06 | 启用/禁用 | 切换 is_active，禁用的 Server 不被 Agent 加载 |
| F-09-07 | 状态跟踪 | connection_status 字段：disconnected/connecting/connected/error |

### 10.4 API 端点

```
GET    /api/v1/mcp/servers             # MCP Server 列表
GET    /api/v1/mcp/servers/:id         # Server 详情
POST   /api/v1/mcp/servers             # 创建 Server
PUT    /api/v1/mcp/servers/:id         # 更新 Server
DELETE /api/v1/mcp/servers/:id         # 删除 Server
POST   /api/v1/mcp/servers/:id/test    # 连接测试
```

### 10.5 审计日志新增

| action | 触发操作 |
|--------|---------|
| `skill:upload` | 上传 Skill ZIP |
| `skill:delete` | 删除 Skill |
| `mcp:create` | 创建 MCP Server |
| `mcp:delete` | 删除 MCP Server |
| `approval:approve` | 审批通过 (Phase 4) |
| `approval:reject` | 审批拒绝 (Phase 4) |

---

## 11. [待实现] F-10 知识库模块 (Phase 2)

> **状态**: 设计中 | **时间**: 3-4 周

### 11.1 功能概述

支持创建知识库集合、上传多种格式文档（PDF/Word/Markdown/TXT），自动解析→分块→Embedding→存储到 pgvector。提供语义搜索 + BM25 关键词 + RRF 融合的混合检索能力。

### 11.2 数据模型

| 表 | 说明 |
|----|------|
| `knowledge_collections` | 知识库集合（embedding_model, chunk_size, chunk_overlap） |
| `knowledge_documents` | 文档（file_type, status: pending→parsing→ready→error, chunk_count） |
| `knowledge_chunks` | 分块向量（自动创建 pgvector 表 `kb_{collection_id}`） |

### 11.3 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-10-01 | 创建集合 | 定义名称、Embedding 模型、分块参数 |
| F-10-02 | 集合列表 | 查看/编辑/删除知识库集合 |
| F-10-03 | 文档上传 | PDF/Word/MD/TXT，异步解析管道 |
| F-10-04 | 文档管理 | 列表/删除/分块预览/状态跟踪 |
| F-10-05 | 混合检索 | 语义搜索+BM25关键词+RRF融合排序 |
| F-10-06 | 检索测试 | 前端检索测试面板 |
| F-10-07 | 检索反馈 | 相关性标注（thumbs up/down） |
| F-10-08 | 引用溯源 | 回答时标明信息来源 |

### 11.4 API 端点

```
POST   /eap/api/v1/knowledge/collections
GET    /eap/api/v1/knowledge/collections
GET    /eap/api/v1/knowledge/collections/:id
PUT    /eap/api/v1/knowledge/collections/:id
DELETE /eap/api/v1/knowledge/collections/:id
POST   /eap/api/v1/knowledge/collections/:id/documents/upload
GET    /eap/api/v1/knowledge/collections/:id/documents
DELETE /eap/api/v1/knowledge/documents/:id
GET    /eap/api/v1/knowledge/documents/:id/chunks
POST   /eap/api/v1/knowledge/search
POST   /eap/api/v1/knowledge/search/feedback
```

---

## 12. [待实现] F-11 多 Agent 编排模块 (Phase 3)

> **状态**: 设计中 | **时间**: 4-5 周

### 12.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-11-01 | 子 Agent 注册 | 定义名称/角色提示词/工具集/模型 |
| F-11-02 | 监督者路由 | Supervisor 根据任务类型自动分发到 Worker |
| F-11-03 | Inline 模式 | 阻塞式委托，父 Agent 等待结果 |
| F-11-04 | Compiled 模式 | 编译为受限工具集，防止越权 |
| F-11-05 | Async 模式 | 非阻塞并行，父 Agent 继续处理 |
| F-11-06 | 编排图可视化 | 前端展示 LangGraph DAG 结构 |
| F-11-07 | 编排测试部署 | 测试编排图 + 一键部署 |

### 12.2 API 端点

```
POST   /eap/api/v1/agents/:id/sub-agents
DELETE /eap/api/v1/agents/:id/sub-agents/:sub_id
POST   /eap/api/v1/agents/:id/orchestration
POST   /eap/api/v1/orchestration/test
POST   /eap/api/v1/orchestration/deploy
```

---

## 13. [待实现] F-12 安全围栏模块 (Phase 4)

> **状态**: 设计中 | **时间**: 3-4 周

### 13.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-12-01 | PII 检测 | 邮箱/手机/身份证/信用卡/IP 正则+ML检测 |
| F-12-02 | PII 脱敏 | redact / mask / hash / block 四种策略 |
| F-12-03 | 内容安全 | 关键词黑名单+危险模式（SQL注入/XSS/命令注入） |
| F-12-04 | 工具拦截 | PreToolUse 围栏：敏感操作拦截 |
| F-12-05 | 输出审查 | 后置 LLM 安全评估与合规扫描 |
| F-12-06 | 围栏链 | 多层堆叠，前置失败即拦截 |
| F-12-07 | 自定义规则 | 管理员可配置自定义围栏规则 |

### 13.2 API 端点

```
GET    /eap/api/v1/admin/guardrails
POST   /eap/api/v1/admin/guardrails
PUT    /eap/api/v1/admin/guardrails/:id
DELETE /eap/api/v1/admin/guardrails/:id
```

---

## 14. [待实现] F-13 人机协同模块 (Phase 4)

> **状态**: 设计中

### 14.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-13-01 | 审批触发配置 | `interrupt_on` 参数指定哪些工具需要审批 |
| F-13-02 | 四种决策 | approve / edit / reject / respond |
| F-13-03 | 条件审批 | 根据工具参数动态决定是否需要审批 |
| F-13-04 | 审批管理 | 待审批列表 + 已审批历史 |
| F-13-05 | 检查点恢复 | Worker 释放→恢复时精确继续 |
| F-13-06 | 角色门控 | 仅特定角色可审批 |
| F-13-07 | 审批 UI | 前端审批卡片：参数预览 + 决策按钮 |

### 14.2 API 端点

```
GET    /eap/api/v1/workflow/approvals
POST   /eap/api/v1/workflow/approvals/:id/approve
POST   /eap/api/v1/workflow/approvals/:id/reject
POST   /eap/api/v1/workflow/approvals/:id/edit
```

---

## 15. [待实现] F-14 长期记忆模块 (Phase 4)

> **状态**: 设计中

### 15.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-14-01 | 记忆存储 | LangGraph Store.put() 持久化到 PostgreSQL |
| F-14-02 | 语义检索 | Embedding 相似度搜索相关记忆 |
| F-14-03 | 三级作用域 | User / Assistant / Organization 粒度隔离 |
| F-14-04 | 自动注入 | MemoryMiddleware 自动注入上下文 |
| F-14-05 | 虚拟文件系统 | `/memories/` 路径暴露给 Agent |

---

## 16. [待实现] F-15 可观测性模块 (Phase 5)

> **状态**: 设计中 | **时间**: 2-3 周

### 16.1 功能清单

| 功能ID | 功能名称 | 描述 |
|--------|---------|------|
| F-15-01 | LangSmith 追踪 | 全链路分布式追踪（模型/工具/子Agent） |
| F-15-02 | OTel 导出 | OTLP 导出到 Jaeger/Tempo |
| F-15-03 | 成本追踪 | Token 消耗按租户/用户/模型/天聚合 |
| F-15-04 | 成本仪表盘 | 趋势图 + 排行榜 + 月度汇总 |
| F-15-05 | 健康检查 | DB+Redis+LLM 综合检测 |
| F-15-06 | 并发监控 | 活跃会话数 + 错误率 + 延迟分布 |
| F-15-07 | 运维仪表盘 | 前端综合面板：指标卡片+图表+日志 |
| F-15-08 | API 文档 | OpenAPI/Swagger 自动生成 |

### 16.2 API 端点

```
GET    /eap/api/v1/admin/monitor/dashboard
GET    /eap/api/v1/admin/monitor/cost/tenant
GET    /eap/api/v1/admin/monitor/cost/user
GET    /eap/api/v1/admin/monitor/usage/agents
GET    /eap/api/v1/admin/monitor/usage/models
GET    /eap/api/v1/admin/monitor/latency
GET    /eap/api/v1/admin/monitor/errors
GET    /eap/api/v1/admin/monitor/concurrency
```

---

## 17. 页面路由映射

| 路由 | 页面 | 权限要求 | Phase |
|------|------|---------|-------|
| `/login` | 登录/注册页 | 无 | P1 ✓ |
| `/chat` | 对话主页 | `agent:execute` | P1 ✓ |
| `/chat/:threadId` | 指定线程对话 | `agent:execute` | P1 ✓ |
| `/agents` | Agent 管理 | `agent:read` | P1 ✓ |
| `/skills` | Skill 市场 | `skill:read` | P1 ✓ |
| `/knowledge` | 知识库管理 | `knowledge:read` | P2 |
| `/knowledge/:id` | 知识库详情 | `knowledge:read` | P2 |
| `/orchestration` | 编排管理 | `agent:create` | P3 |
| `/approvals` | 审批中心 | `approval:approve` | P4 |
| `/admin/models` | 模型配置 | `admin:settings` | P1 ✓ |
| `/admin/mcp` | MCP 服务 | `mcp:read` | P1 ✓ |
| `/admin/users` | 用户管理 | `user:read` | P1 ✓ |
| `/admin/roles` | 角色管理 | `user:read` | P1 ✓ |
| `/admin/audit` | 审计日志 | `admin:audit` | P1 ✓ |
| `/admin/guardrails` | 安全围栏 | `admin:settings` | P4 |
| `/admin/monitor` | 系统监控 | `admin:access` | P5 |

### 17.1 侧边栏菜单

```
├── 对话 (/chat)              ✓ P1
├── Agent 管理 (/agents)      ✓ P1
├── Skill 市场 (/skills)      ✓ P1
├── 知识库 (/knowledge)         P2
├── 编排管理 (/orchestration)   P3
├── 审批中心 (/approvals)       P4
└── 管理后台
    ├── 模型配置 (/admin/models)    ✓ P1
    ├── MCP 服务 (/admin/mcp)       ✓ P1
    ├── 用户管理 (/admin/users)     ✓ P1
    ├── 安全围栏 (/admin/guardrails)  P4
    └── 系统监控 (/admin/monitor)     P5
```

---

## 附录：数据模型字典

| 表名 | 说明 | 租户隔离 |
|------|------|---------|
| `tenants` | 租户（企业/组织） | — |
| `users` | 用户 | `tenant_id` FK |
| `roles` | 角色（系统级tenant_id=NULL，租户级有值） | `tenant_id` FK/null |
| `permissions` | 权限点（全局共享） | 无 |
| `user_roles` | 用户-角色关联表 | — |
| `role_permissions` | 角色-权限关联表 | — |
| `agent_configs` | Agent 配置 | `tenant_id` FK |
| `model_providers` | 模型供应商配置 | `tenant_id` FK |
| `skill_configs` | Skill 上传配置 | `tenant_id` FK |
| `mcp_servers` | MCP Server 配置 | `tenant_id` FK |
| `knowledge_collections` | 知识库集合 (P2) | `tenant_id` FK |
| `knowledge_documents` | 知识库文档 (P2) | `tenant_id` FK |
| `knowledge_chunks` | 分块向量 (P2) | `tenant_id` FK |
| `guardrail_rules` | 安全围栏规则 (P4) | `tenant_id` FK |
| `approval_requests` | 审批请求 (P4) | `tenant_id` FK |
| `audit_logs` | 审计日志 | `tenant_slug` 索引 |

---

## 18. 阶段交付矩阵

| Phase | 时间 | 功能模块 | 功能点 | 状态 |
|-------|------|---------|--------|------|
| **P1** | 4-6 周 | F-01~F-09 | 认证/RBAC/对话/Agent/模型/Skill/MCP | ✅ 已实现 |
| **P2** | 3-4 周 | F-10 知识库 | 集合/文档/混合检索/RAG Agent/检索反馈 | 🔲 设计中 |
| **P3** | 4-5 周 | F-11 多Agent编排 | 子Agent/监督者路由/编排图/测试部署 | 🔲 设计中 |
| **P4** | 3-4 周 | F-12~F-14 | 安全围栏/人机协同/长期记忆 | 🔲 设计中 |
| **P5** | 2-3 周 | F-15 可观测性 | 追踪/成本/仪表盘/API文档 | 🔲 设计中 |
| **合计** | **16-22 周** | **19 个模块** | **100+ 功能点** | |
