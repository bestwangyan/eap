# EAP 编排核心 deepagents 化 — 设计文档

- 日期：2026-08-30
- 分支：`deepagent`（独立于 main 开发）
- 状态：设计已确认，待实施计划

## 1. 目标

用 `deepagents`（langchain-ai/deepagents，PyPI 包 `deepagents==0.7.11`）**完全替换**现有手写 LangGraph 编排核心（`orchestrator.py` 的图构建部分），充分启用其特性：执行 backend（本地文件系统 / Docker 容器沙箱）、skills 渐进披露、subagents（独立模型）、记忆文件、规划与上下文自动管理。**对外接口不变**：SSE 协议、前端、聊天页、监控面板全部零改动；现有能力（多租户、RBAC、安全围栏、双持久化、全局记忆、知识库、MCP、trace 监控、模型通道绑定）充分整合。

## 2. 已确认的决策

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 替换策略 | 完全替换：stream_chat 改用 deepagents 图，旧图构建代码退役 |
| 2 | backend 落地 | local + container 双实现：local → FilesystemBackend（租户隔离目录）；container → 自研 DockerBackend（SandboxBackendProtocol） |
| 3 | 子 Agent 映射 | sub_agent 表加 `model_provider_id`（独立模型），映射为 deepagents subagents dict |
| 4 | Skill 映射 | `agent` 模式 → subagent（语义升级）；`prompt` 模式 → deepagents skills 渐进披露 |
| 5 | 记忆体系 | 双层：保留 DB 全局记忆（user_memory 表 + 工具 + 注入）；新增 deepagents memory 文件（每用户，随 backend 根目录持久化） |

## 3. 架构总览

```
stream_chat（对外协议不变：SSE 事件/围栏/运行时上下文/trace 照旧）
  │
  ├─ DeepAgentFactory（新）：读 AgentConfig/SubAgentDefinition/SkillConfig
  │   组装 create_deep_agent(...) → 返回编译图 + 缓存键
  │
  └─ graph.stream(stream_mode=["messages","updates"]) → 现有 SSE 映射逻辑
```

- 编排核心：`create_deep_agent` 替换手写 StateGraph；默认中间件栈（todos / memory / skills / filesystem / subagents / summarization）全部启用
- 模型：现有 `_build_llm` 不变（DeepSeek/OpenAI/Anthropic/LM Studio 通道 + 智能体 `model_provider_id` 绑定 + `stream_usage`），实例直接传入 deepagents 的 `model` 参数
- 检查点：现有 PostgresSaver 原样传入 → 双持久化、断点续聊、一致性校验全部保留
- 安全围栏：GuardrailChain 仍在 chat.py + orchestrator 入口（不依赖 deepagents middleware），现状零改动
- 监控：DBTraceHandler 继续作为 callbacks 传入，trace/token 统计不动

## 4. 现有能力 → deepagents 映射

| 现有能力 | 映射到 | 说明 |
|---|---|---|
| 内置工具集（calculator/datetime/web_search/code_execution/knowledge_search/memory_save/memory_search/read_skill_file） | `tools` 参数 | 全部保留，按 agent 的 tools_config 过滤；与 deepagents 默认文件工具、task 并存 |
| 子 Agent（SubAgentDefinition） | `subagents` dict | 表加 `model_provider_id` 实现独立模型；`sub_agent_x` 工具退役，改用 deepagents 原生 `task` 工具调度 |
| `agent` 模式 Skill | subagent | 独立上下文 + 可配工具，取代现有 `skill_xxx` LLM 包装工具 |
| `prompt` 模式 Skill | `skills` 目录路径 | 磁盘存储结构（SKILL.md + resources）天然兼容，从全量注入升级为渐进披露 |
| 全局记忆 | 保留 DB 工具 | user_memory 表 + memory_save/search + 高重要性条目注入系统提示词不变 |
| deepagents 新记忆 | `memory` 文件 | 每用户一个记忆文件，放 backend 根目录（容器模式挂宿主卷持久化） |
| `backend` 字段（local/container） | 执行后端 | local → FilesystemBackend；container → DockerBackend |
| MCP 工具 | `tools` 参数 | 现有 MultiServerMCPClient 缓存机制不变 |
| 图缓存 | 缓存键扩展 | `provider:model:tools:skills:subagents:backend` 指纹（含端点哈希） |

## 5. 执行后端设计

### 5.1 local — FilesystemBackend

- `root_dir = /home/wangyan/deploy/eap/agent_workspaces/{tenant_id}/{user_id}/{thread_id}/`
- 文件工具（ls/read_file/write_file/edit_file/glob/grep）可用；shell（execute）不可用 —— deepagents 对非沙箱 backend 的 execute 天然返回错误
- 用途：无 Docker 依赖的保底模式；文件操作隔离在租户/用户/线程目录内

### 5.2 container — DockerBackend（自研，实现 SandboxBackendProtocol）

- 一次性容器 `python:3.12-slim`，参数：`--rm --network none --memory 256m --cpus 1 --pids-limit 64`
- 文件持久化：宿主目录（同 5.1 的 root_dir）挂载到容器 `/workspace`
- `execute` 在容器内执行，超时沿用 10s；超限/失败作为工具结果返回给 LLM
- 构建失败（Docker 不可用、镜像缺失）→ **fail-closed**：error 事件明确报错，绝不静默回退宿主机执行
- 镜像预热：首次部署时 `docker pull python:3.12-slim`（服务器已有 Docker）

## 6. 数据流与 SSE 协议（前端零改动）

```
浏览器 → Nginx → chat.py（围栏输入检查，不变）
  → orchestrator.stream_chat（围栏纵深，不变）
    → 组装 deepagent（按缓存键复用编译图）
    → graph.stream(input, config, stream_mode=["messages","updates"])
      messages 流 → token 事件（打字机式流式，不变）
      updates 流 → tool_start/tool_end/done + usage + trace_id（不变）
  → chat.py（围栏输出检查 + 落库 + 成本记录，不变）
```

- deepagents 内置工具（write_todos/ls/read_file/write_file/edit_file/glob/grep/execute/task）的 tool_start/end 事件按原名展示，前端 ToolRow 无需改动
- **技术验证点（实施第一步）**：deepagents 图的 updates 流节点输出结构是否与现有 SSE 映射逻辑兼容；不兼容则在 orchestrator 事件映射层适配，不改前端

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| backend 构建失败（Docker 不可用/镜像缺失） | fail-closed：明确 error 事件，绝不静默回退宿主机执行 |
| local 模式 shell 执行 | deepagents 自身拒绝（非沙箱 backend 下 execute 返回错误） |
| 容器执行超时/资源超限 | 10s 超时 + --memory 限制，错误作为 tool_end 结果返回给 LLM |
| 围栏异常 | fail-open（现状不变） |
| 依赖冲突（langchain-core 1.5.4 → 1.6.x） | 部署前服务器 venv dry-run + 全量回归；冲突则锁定兼容版本组合并记录 |

## 8. 新文件结构

```
backend/app/core/agent/
├── deep_agent_factory.py     # 组装 create_deep_agent（新）
├── backends/
│   ├── __init__.py           # build_backend(tenant, user, thread, mode)
│   ├── docker_backend.py     # DockerBackend(SandboxBackendProtocol)（新）
│   └── filesystem_backend.py # 租户隔离目录包装（薄封装，新）
└── orchestrator.py           # 瘦身：删除 _get_or_build_graph / _build_skill_tools /
                              #       _build_sub_agent_tools，图构建委托 factory
```

其余改动：
- `app/models/sub_agent.py`：加 `model_provider_id` 列（FK → model_providers）
- `app/api/v1/orchestration.py`：子 agent create/update 接受 model_provider_id
- 前端 AgentManager：子 agent 表单加"模型后端"下拉（动态加载可用模型供应商）
- `backend/requirements.txt`：`deepagents==0.7.11`（解除注释并升版），连带 langchain/langchain-core/langchain-anthropic 版本约束更新

## 9. 依赖升级

| 包 | 现状（服务器） | 目标 |
|---|---|---|
| deepagents | 未安装 | 0.7.11 |
| langchain-core | 1.5.4 | >=1.6.1（deepagents 要求） |
| langchain | 1.3.15 | >=1.3.18（deepagents 要求） |
| langchain-anthropic | 1.5.5 | >=1.7.0（deepagents 要求） |

服务器双 venv 安装 + 符号链接沿用既有部署模式（deploy-eap skill 陷阱 2）。

## 10. 测试与迁移

**迁移步骤**（实施计划阶段细化）：
1. 装包 + 冒烟验证 deepagents 图（流式/工具/checkpointer/updates 结构）
2. 实现 backends（filesystem → docker）
3. 实现 DeepAgentFactory + orchestrator 瘦身
4. 子 agent 表加 model_provider_id + API + 前端下拉
5. 全量回归（现有 66 项用例不删 —— 它们验证协议与集成）+ 新增 deepagents 特性用例

**新增测试用例**：
- 文件工具闭环：一轮对话内 write_file → read_file 验证内容
- 容器后端：container 模式下 execute 执行 `print(2**10)` 返回 1024
- 子 agent 独立模型：绑定 LM Studio 的子 agent 被 task 调度
- prompt skill 渐进披露：skill 目录被加载且对话可用

**验收标准**：现有 66 项回归全绿 + 新增用例全绿 + 前端聊天页完整对话冒烟（含容器模式 agent）。

## 11. 范围外（YAGNI）

- 不做双轨并存（旧编排器退役，不保留 runtime 切换字段）
- 不引入 LangSmithSandbox（私有部署，无 LangSmith 账号）
- 不迁移 prompt 模式 skill 的"全量注入"行为到别处（统一渐进披露）
- 子 agent 不升级为 CompiledSubAgent 全功能模式（dict 形式够用，避免复杂度）
