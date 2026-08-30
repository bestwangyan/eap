"""
Agent 编排器 — EAP 对话系统的核心引擎。

================================================================================
架构概览
================================================================================

本模块负责管理 deepagents 编译图的完整生命周期，是连接 Flask Web 层和 LLM 的桥梁。

调用链：
  Flask chat.py (SSE stream)
    → AgentOrchestrator.stream_chat()
      → _resolve_provider_config()   # 确定用哪个模型/API Key
      → DeepAgentFactory.build()     # 组装 deepagents 编译图（带缓存）
      → _build_system_prompt()       # 拼接 Agent 提示词 + Skill 规则
      → graph.stream()               # 执行 deepagents 图，逐节点产出 SSE 事件
        → model  (LLM 推理 + 工具调用决策)
        → tools  (ToolNode：deepagents 默认工具 + EAP 工具 + 子代理 task)
        → 循环直到 LLM 不再请求工具

图结构与中间件（create_deep_agent 内置）：
  model → tools → model → ...（HITL/文件系统/技能/记忆等中间件挂载在两侧钩子）

  - checkpointer：PostgreSQL 存储对话历史，支持断点续聊
  - 编译图缓存归 DeepAgentFactory：键含 provider/model + 工具指纹 +
    后端模式 + 子代理 + 线程 + 租户（线程工作目录编译期烘焙，不可跨线程复用）

关键设计决策：

  1. 双流模式 stream_mode=["messages", "updates"]
     "messages" 流提供 LLM 逐 token 的文本增量（打字机式流式输出）
     "updates" 流提供节点完成后的完整状态（工具调用完整参数 + 用量元数据）
     只用 messages 模式时工具参数在 chunk 中为空；只用 updates 时
     整段回复一次性到达（无流式效果）——双流各取所长

  2. 工具集三源合一
     EAP 自有工具（DEFAULT_TOOLS 过滤 + MCP）由 _resolve_tools 解析后
     作为 factory.build(tools=...) 传入；deepagents 默认工具
     （ls/read_file/write_file/edit_file/glob/grep/execute/task/write_todos）
     由 create_deep_agent 自动追加；agent 模式 Skill 与子代理组装为
     deepagents subagents（经 task 工具委派）

  3. 同步生成器，非 async
     deepagents 图的 stream() 是同步迭代器，与 Flask SSE + gevent 兼容
================================================================================
"""

import json
import logging
from flask import current_app
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.core.agent.deep_agent_factory import TOOL_DISPLAY_NAMES
from app.core.agent.tools import DEFAULT_TOOLS
from app.core.agent.prompts.system import DEFAULT_SYSTEM_PROMPT
from app.core.monitoring.trace_callback import DBTraceHandler, set_trace_context

logger = logging.getLogger(__name__)


def _delete_checkpoint_by_tid(checkpointer, thread_id: str) -> int:
    """
    SQL 直删 checkpoints/blobs/writes 三表，返回删除行数。

    采用 psycopg3 直连（非连接池）执行 DELETE，因为 CHECKPOINT 表上
    CREATE INDEX CONCURRENTLY 可能使连接池中的连接处于事务状态，
    导致 autocommit 设置不生效。
    """
    try:
        import psycopg
        pool = getattr(checkpointer, "conn", None)
        if not pool:
            return 0
        conn = psycopg.connect(pool.conninfo, autocommit=True)
        deleted = 0
        try:
            with conn.cursor() as cur:
                # 必须按外键依赖顺序：先子表，后主表
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    cur.execute(f"DELETE FROM {table} WHERE thread_id = %s", (thread_id,))
                    deleted += cur.rowcount
        finally:
            conn.close()
        return deleted
    except Exception as e:
        logger.warning(f"Failed to delete checkpoint for {thread_id}: {e}")
        return 0


def _cleanup_stale_checkpoint(checkpointer, thread_id: str) -> None:
    """
    检查并清理残缺的检查点状态。

    当子Agent/Skill/MCP 工具执行超时导致 HTTP 请求中断时，
    LangGraph 的 checkpointer 可能只保存了 AIMessage(tool_calls)
    而没有对应的 ToolMessage。后续继续对话时，DeepSeek 会因
    "insufficient tool messages following tool_calls message" 拒绝请求。

    必须用 LangGraph 的 get_tuple() API 读取状态（消息体序列化在
    checkpoint_blobs 表中，SQL 直读 JSON 拿不到），检测到残缺状态时
    调用 _delete_checkpoint_by_tid 清除整条线程记录。
    """
    if not checkpointer:
        return

    try:
        # 必须用 LangGraph 的 API 读取状态（消息体存在 checkpoint_blobs 表中）
        config = {"configurable": {"thread_id": thread_id}}
        state = checkpointer.get_tuple(config)
        if not state or not state.checkpoint:
            return

        msgs = state.checkpoint.get("channel_values", {}).get("messages", [])
        if not msgs:
            return

        last_msg = msgs[-1]
        tc = getattr(last_msg, "tool_calls", None) if hasattr(last_msg, "tool_calls") else None
        if not tc:
            return

        # 检查 tool_calls 是否有对应的 ToolMessage
        tc_count = len(tc)
        recent = msgs[-tc_count - 1:]
        has_response = any(
            hasattr(m, "tool_call_id") and m.tool_call_id
            for m in recent
        )

        if not has_response:
            logger.warning(
                f"Thread {thread_id}: detected stale tool_calls "
                f"({tc_count} call(s)), cleaning checkpoint"
            )
            _delete_checkpoint_by_tid(checkpointer, thread_id)
    except Exception as e:
        logger.debug(f"Stale checkpoint check skipped: {e}")


class AgentOrchestrator:
    """
    Agent 编排器 —— 管理 LangGraph Agent 的完整生命周期。

    职责：
      1. 根据模型配置构建 LLM 实例（支持 Anthropic/OpenAI/DeepSeek）
      2. 构建并缓存 LangGraph 状态图（agents + tools 的有向执行图）
      3. 解析模型选择优先级（用户指定 > 默认 > 环境变量兜底）
      4. 注入 Agent 自定义提示词和 Skill 规则到系统消息
      5. 流式输出 SSE 事件（token / tool_start / tool_end / done / error）
      6. 集成 Trace 回调，记录每次 LLM/Tool 调用到数据库

    使用方式：
      orch = AgentOrchestrator(checkpointer=PostgresSaver(pool))
      for sse in orch.stream_chat(user_message="你好", thread_id="...", ...):
          # sse 是 "data: {...}\n\n" 格式的 SSE 字符串
          yield sse
    """

    def __init__(self, checkpointer: PostgresSaver = None):
        """
        Args:
            checkpointer: LangGraph PostgresSaver 实例。
                          传入 None 时对话历史仅存内存，进程重启后丢失。
        """
        self._checkpointer = checkpointer
        self._tools = DEFAULT_TOOLS
        # 编译图缓存归 DeepAgentFactory（键含 provider/model + 工具指纹 +
        # 后端模式 + 子代理 + 线程 + 租户，见 deep_agent_factory._cache_key）
        self._deep_factory = None
        # MCP 工具缓存：key = "{tenant_id}:{agent_id}"，避免每次请求
        # 重新创建 MCP 客户端（stdio 模式会 spawn 子进程且无法关闭）
        self._mcp_tools_cache: dict[str, list] = {}

    # =========================================================================
    # LLM 构建
    # =========================================================================

    def _build_llm(self, provider_config: dict):
        """
        根据 provider_config 构建 LangChain ChatModel 实例。

        provider_config 结构（由 _resolve_provider_config 产出）：
          {
            "provider":    "deepseek" | "openai" | "anthropic" | "lmstudio",
            "model_name":  "deepseek-v4-pro" | "gpt-4o" | ...,
            "api_key":     "sk-...",
            "api_base":    "https://api.deepseek.com/v1" | "" (可选),
          }

        DeepSeek / OpenAI / LM Studio 共用 ChatOpenAI 类（三者 API 均兼容
        OpenAI 格式），区别仅在于 base_url 指向不同的 API 端点。

        返回的 LLM 实例配置了 max_tokens=4096 和 temperature=0.7，
        适合企业场景：控制成本 + 保持回答的稳定性和准确性。
        """
        provider = provider_config["provider"]
        model_name = provider_config["model_name"]
        api_key = provider_config["api_key"]
        api_base = provider_config.get("api_base", "")

        if provider == "anthropic":
            return ChatAnthropic(
                model=model_name,
                api_key=api_key,
                max_tokens=4096,
                temperature=0.7,
            )
        elif provider == "openai":
            kwargs = dict(
                model=model_name,
                api_key=api_key,
                max_tokens=4096,
                temperature=0.7,
                # 流式时请求服务端在最后一个 chunk 返回 usage
                # （OpenAI 兼容 API 的 token 统计依赖此开关，LM Studio 尤其需要）
                stream_usage=True,
            )
            if api_base:
                kwargs["base_url"] = api_base
            return ChatOpenAI(**kwargs)
        elif provider == "deepseek":
            # DeepSeek API 兼容 OpenAI SDK，通过 base_url 区分
            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=api_base or "https://api.deepseek.com/v1",
                max_tokens=4096,
                temperature=0.7,
                stream_usage=True,
            )
        elif provider == "lmstudio":
            # LM Studio 本地模型服务器 — OpenAI 兼容 API
            # 默认地址 http://127.0.0.1:1234/v1（LM Studio 默认端口）
            # API Key 本地服务不校验，任意非空值即可（占位 "lm-studio"）
            return ChatOpenAI(
                model=model_name,
                api_key=api_key or "lm-studio",
                base_url=api_base or "http://127.0.0.1:1234/v1",
                max_tokens=4096,
                temperature=0.7,
                stream_usage=True,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    # =========================================================================
    # 工具集解析（Agent 差异化的核心）
    # =========================================================================

    def _build_mcp_tools(self, agent_id: int | None, tenant_id: str) -> list:
        """
        为 Agent 加载其关联的 MCP Server 工具。

        从 mcp_servers 表读取 Agent 配置的 MCP 服务，通过
        langchain_mcp_adapters 的 MultiServerMCPClient 获取远端工具列表。
        支持 stdio（本地子进程）和 SSE（远程 HTTP）两种传输。

        MCP 工具和 Agent 内置工具统一注入到工具集，LLM 以相同方式调用。
        连接失败时记录 warning 但不阻塞对话。
        """
        if not agent_id:
            return []

        # 命中缓存直接返回 — stdio 模式每次重建客户端会 spawn 新子进程
        cache_key = f"{tenant_id}:{agent_id}"
        if cache_key in self._mcp_tools_cache:
            return self._mcp_tools_cache[cache_key]

        try:
            from app.models.agent_config import AgentConfig

            agent = AgentConfig.query.filter_by(
                id=agent_id, tenant_id=int(tenant_id)
            ).first()
            if not agent or not agent.mcp_servers:
                self._mcp_tools_cache[cache_key] = []
                return []

            # 加载已激活的 MCP Server
            from app.models.mcp_server import MCPServer
            servers = MCPServer.query.filter(
                MCPServer.tenant_id == int(tenant_id),
                MCPServer.name.in_(agent.mcp_servers),
                MCPServer.is_active == True,
            ).all()

            if not servers:
                self._mcp_tools_cache[cache_key] = []
                return []

            # 构建 MultiServerMCPClient 配置
            mcp_config: dict[str, dict] = {}
            for srv in servers:
                try:
                    mcp_config[srv.name] = srv.to_mcp_config()
                except ValueError as e:
                    logger.warning(f"MCP config error for {srv.name}: {e}")

            if not mcp_config:
                self._mcp_tools_cache[cache_key] = []
                return []

            # 创建客户端并获取工具（async → sync via asyncio）
            # 客户端常驻进程生命周期，stdio 子进程复用连接
            import asyncio
            from langchain_mcp_adapters.client import MultiServerMCPClient

            client = MultiServerMCPClient(mcp_config)
            tools = asyncio.run(client.get_tools())
            # 保存客户端引用，防止其被 GC 后关闭子进程
            self._mcp_clients = getattr(self, "_mcp_clients", {})
            self._mcp_clients[cache_key] = client

            logger.info(
                f"Loaded {len(tools)} MCP tools from {len(mcp_config)} server(s): "
                f"{list(mcp_config.keys())}"
            )
            self._mcp_tools_cache[cache_key] = list(tools)
            return self._mcp_tools_cache[cache_key]

        except Exception as e:
            logger.warning(f"Failed to build MCP tools: {e}")
            self._mcp_tools_cache[cache_key] = []
            return []

    def _resolve_tools(self, agent_id: int | None, tenant_id: str,
                      model_provider_id: int | None = None) -> list:
        """
        根据 Agent 配置解析 EAP 自有工具列表（DEFAULT_TOOLS 过滤 + MCP 工具）。

        默认（无 agent_id 或 agent 未配置 tools_config）：
          → 返回全部 DEFAULT_TOOLS

        Agent 配置了 tools_config（如 ["calculator", "web_search"]）：
          → 从 DEFAULT_TOOLS 中筛选出匹配的工具
          → 工具名不存在于 DEFAULT_TOOLS 中的会跳过并记录 warning
            （code_execution 名字保留为 execute 启用开关，本身不再解析）

        skill/sub-agent 工具构建已随 deepagents 迁移删除：agent 模式
        Skill 与子代理改由 DeepAgentFactory 组装为 deepagents subagents
        （经内置 task 工具委派）。返回结果整体交给
        factory.build(tools=...) 作为最终 EAP 工具集，deepagents 默认
        工具（ls/read/execute/task 等）由 create_deep_agent 追加。
        """
        if not agent_id:
            return list(self._tools)

        try:
            from app.models.agent_config import AgentConfig

            agent = AgentConfig.query.filter_by(
                id=agent_id, tenant_id=int(tenant_id)
            ).first()

            if not agent or not agent.tools_config:
                return list(self._tools)

            # 按名称过滤：只保留 Agent 配置中声明的工具
            requested = set(agent.tools_config)
            tool_map = {t.name: t for t in self._tools if hasattr(t, "name")}
            resolved = []
            for name in requested:
                if name in tool_map:
                    resolved.append(tool_map[name])
                else:
                    logger.warning(
                        f"Agent {agent_id} requested tool '{name}' "
                        f"but it is not available in DEFAULT_TOOLS"
                    )

            # 补充 MCP Server 工具
            mcp_tools = self._build_mcp_tools(agent_id, tenant_id)
            resolved.extend(mcp_tools)

            # 如果所有配置的工具都不存在，回退到全部默认工具
            return resolved if resolved else list(self._tools)

        except Exception as e:
            logger.warning(f"Failed to resolve tools for agent {agent_id}: {e}")
            return list(self._tools)

    # =========================================================================
    # 模型配置解析
    # =========================================================================

    def _resolve_provider_config(self, tenant_id: str, model_provider_id: int | None = None) -> dict:
        """
        三级优先级解析模型配置：

          优先级 1 (最高): 用户在对话页面手动选择的模型
            → 从 model_providers 表按 ID 精确查询，校验 is_active 状态

          优先级 2: 租户默认模型
            → 从 model_providers 表查询 is_default=True 的记录

          优先级 3 (兜底): 环境变量
            → 优先 DEEPSEEK_API_KEY → LLM_PROVIDER + LLM_MODEL

        返回统一格式的 provider_config dict，供 _build_llm() 使用。
        """
        from app.models.model_provider import ModelProvider

        # 优先级 1：用户指定
        if model_provider_id:
            mp = ModelProvider.query.filter_by(
                id=model_provider_id, tenant_id=tenant_id, is_active=True
            ).first()
            if mp:
                return {
                    "provider": mp.provider,
                    "model_name": mp.model_name,
                    "api_key": mp.api_key,
                    "api_base": mp.api_base,
                }

        # 优先级 2：租户默认模型
        mp = ModelProvider.get_default(int(tenant_id))
        if mp:
            return {
                "provider": mp.provider,
                "model_name": mp.model_name,
                "api_key": mp.api_key,
                "api_base": mp.api_base,
            }

        # 优先级 3：环境变量兜底
        deepseek_key = current_app.config.get("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            return {
                "provider": "deepseek",
                "model_name": "deepseek-v4-pro",
                "api_key": deepseek_key,
                "api_base": "https://api.deepseek.com/v1",
            }
        return {
            "provider": current_app.config["LLM_PROVIDER"],
            "model_name": current_app.config["LLM_MODEL"],
            "api_key": deepseek_key or current_app.config.get("ANTHROPIC_API_KEY", "") or current_app.config.get("OPENAI_API_KEY", ""),
            "api_base": "",
        }

    # =========================================================================
    # 系统提示词构建（Agent 自定义 + Skill 规则注入）
    # =========================================================================

    def _build_system_prompt(self, agent_id: int | None, tenant_id: str, user_id: str = "") -> str:
        """
        构建最终的系统提示词，由三层拼接而成：

          第 1 层: DEFAULT_SYSTEM_PROMPT（全局基础规则）
            → 定义 AI 助手的核心行为准则（专业/安全/诚实/高效）

          第 1.5 层: 用户全局记忆（跨线程持久化上下文）
            → 从 user_memories 表加载当前用户的重要记忆，注入为 "<用户记忆>" 章节

          第 2 层: Agent 自定义 system_prompt（Agent 专属指令）
            → 从 agent_configs 表读取，管理员在创建 Agent 时填写
            → 例如："你是一个专注于金融分析的助手..."

          第 3 层: Skill 规则注入
            → 从 agent_configs.skills 列表出发，查询 skill_configs 表
            → 将每个激活 Skill 的 Prompt 内容（SKILL.md 中 frontmatter 之后的部分）
              拼接为 "可用 Skill" 章节
            → 例如：translator skill 会注入：
              "你是一个专业的多语言翻译助手。\n当用户需要翻译时：\n1. 识别源语言和..."

        合并后的系统提示词通过 stream_chat() 作为首条 SystemMessage 注入。
        由于 agent_node 检测到已有 SystemMessage，不会再次插入默认提示词。
        """
        prompt_parts = [DEFAULT_SYSTEM_PROMPT]

        # --- 第 1.5 层：用户全局记忆（跨线程上下文）---
        if user_id:
            try:
                from app.models.user_memory import UserMemory
                memories = UserMemory.query.filter_by(
                    tenant_id=int(tenant_id), user_id=int(user_id),
                ).filter(
                    UserMemory.importance >= 5,
                ).order_by(
                    UserMemory.importance.desc(), UserMemory.updated_at.desc()
                ).limit(10).all()

                if memories:
                    memory_lines = ["## 关于当前用户\n"]
                    for m in memories:
                        memory_lines.append(
                            f"- [{m.category}] {m.key}: {m.content[:200]}"
                        )
                    prompt_parts.append("\n".join(memory_lines))
            except Exception as e:
                logger.warning(f"Failed to load user memories: {e}")

        if agent_id:
            try:
                from app.models.agent_config import AgentConfig
                from app.models.skill_config import SkillConfig

                agent = AgentConfig.query.filter_by(
                    id=agent_id, tenant_id=int(tenant_id)
                ).first()

                if agent:
                    # 第 2 层：Agent 自定义提示词
                    if agent.system_prompt:
                        prompt_parts.append(f"\n## Agent 专属指令\n{agent.system_prompt}")

                    # 第 3 层：Skill 规则
                    skill_names = agent.skills or []
                    if skill_names:
                        # 加载已激活的 Skill，按 mode 分流：
                        #   mode="prompt" → 注入系统提示词（此处）
                        #   mode="agent"  → 组装为 deepagents subagent
                        #     （DeepAgentFactory._skill_subagent，经 task 工具委派）
                        skills = SkillConfig.query.filter(
                            SkillConfig.tenant_id == int(tenant_id),
                            SkillConfig.name.in_(skill_names),
                            SkillConfig.is_active == True,
                            SkillConfig.mode == "prompt",
                        ).all()
                        if skills:
                            skill_prompts = []
                            for s in skills:
                                p = s.get_prompt()
                                if not p:
                                    continue
                                parts = [f"### {s.name}\n{s.description}\n\n{p}"]
                                # 注入 bundled 参考文档
                                inline = s.get_inline_context()
                                if inline:
                                    parts.append(f"\n**参考文档：**\n{inline}")
                                manifest = s.get_on_demand_manifest()
                                if manifest:
                                    parts.append(manifest)
                                skill_prompts.append("\n".join(parts))
                            if skill_prompts:
                                prompt_parts.append(
                                    f"\n## 可用 Skill\n\n"
                                    f"以下 Skill 定义了你的行为规则，你必须严格遵循：\n\n"
                                    + "\n\n".join(skill_prompts)
                                )
            except Exception as e:
                logger.warning(f"Failed to load agent skills: {e}")

        return "\n".join(prompt_parts)

    # =========================================================================
    # 流式对话主入口
    # =========================================================================

    def stream_chat(
        self,
        user_message: str,
        thread_id: str,
        user_id: str,
        tenant_id: str,
        model_provider_id: int | None = None,
        agent_id: int | None = None,
    ):
        """
        流式对话主入口 —— 接收用户消息，逐条产出 SSE 事件。

        SSE 事件类型：
          thread_id:  后端生成的对话 UUID（新对话时作为第一条事件发送）
          token:      LLM 输出的文本片段（逐 token 流式推送）
          tool_start: 工具调用开始（含完整调用参数）
          tool_end:   工具调用完成（含执行结果）
          done:       本轮对话结束（含 token 用量统计）
          error:      异常中断（含错误信息）

        执行流程：
          1. 解析模型配置（三级优先级）
          2. DeepAgentFactory 组装 deepagents 编译图（带缓存）
          3. 设置运行时上下文（供工具函数获取 tenant_id 等）
          4. 创建 Trace 回调（记录 LLM/Tool 事件到 trace_events 表）
          5. 构建系统提示词（Agent + Skill）
          6. 向 LangGraph 发送 [SystemMessage, HumanMessage]
          7. 迭代 graph.stream() 的节点更新，逐个格式化 SSE 事件
          8. 收集 token 用量，在 done 事件中返回

        为什么用 stream_mode="updates" 而不是 "messages"？
          "messages" 模式输出的是 LLM 流式 token chunk，
          当 LLM 生成 tool_call 时，单个 chunk 中 tool_call 的 args 可能不完整。
          "updates" 模式等每个节点执行完毕后输出完整状态，
          此时 tool_call 的 name + args 都是完整的，前端可以准确展示。

        为什么是同步生成器而不是 async？
          LangGraph 的 stream() 是同步迭代器。
          Flask 使用 gevent worker 时，同步代码天然支持 SSE 流式响应。
        """

        # ------------------------------------------------------------------
        # Step 1: 解析模型供应商（有效优先级）
        #   聊天页手动选择 > 智能体绑定的 model_provider_id > 租户默认 > 环境变量
        # ------------------------------------------------------------------
        effective_provider_id = model_provider_id
        if not effective_provider_id and agent_id:
            try:
                from app.models.agent_config import AgentConfig
                _agent = AgentConfig.query.filter_by(
                    id=agent_id, tenant_id=int(tenant_id)
                ).first()
                if _agent and _agent.model_provider_id:
                    effective_provider_id = _agent.model_provider_id
            except Exception:
                pass

        provider_config = self._resolve_provider_config(tenant_id, effective_provider_id)
        # _llm 与 _checkpointer 供 DeepAgentFactory 使用
        provider_config["_llm"] = self._build_llm(provider_config)
        provider_config["_checkpointer"] = self._checkpointer

        # ------------------------------------------------------------------
        # Step 2: 组装 deepagent 图（DeepAgentFactory，带缓存）
        #   _resolve_tools 返回 EAP 自有工具（DEFAULT_TOOLS 过滤）+ MCP 工具，
        #   整体作为 factory.build 的 tools 参数；deepagents 默认工具
        #   （ls/read_file/write_file/edit_file/glob/grep/execute/task 等）
        #   由 create_deep_agent 自动追加。
        # ------------------------------------------------------------------
        from app.core.agent.deep_agent_factory import DeepAgentFactory
        factory = self._deep_factory or DeepAgentFactory()
        self._deep_factory = factory
        agent_tools = self._resolve_tools(agent_id, tenant_id, effective_provider_id)
        graph, _cache_key = factory.build(
            tenant_id, agent_id, user_id, provider_config, thread_id,
            tools=agent_tools)

        # ------------------------------------------------------------------
        # Step 3: 设置运行时上下文
        # 工具函数（如 knowledge_search）在 LangGraph ToolNode 中执行，
        # 此时不在 Flask 请求上下文内，无法通过 flask.g 获取租户信息。
        # 通过 contextvars 将 tenant_id/user_id 传递给工具函数。
        # 同时加载 Agent 配置的 knowledge_collections，供 knowledge_search 工具过滤
        # ------------------------------------------------------------------
        from app.core.agent.runtime_context import set_runtime_context
        kb_ids = None
        backend = None
        if agent_id:
            try:
                from app.models.agent_config import AgentConfig
                agent = AgentConfig.query.filter_by(
                    id=agent_id, tenant_id=int(tenant_id)
                ).first()
                if agent:
                    if agent.knowledge_collections:
                        kb_ids = agent.knowledge_collections
                    # 执行后端（预留）：后续容器沙箱实现后，工具通过 get_backend() 感知
                    backend = agent.backend or "local"
            except Exception:
                pass
        set_runtime_context(
            tenant_id=tenant_id, user_id=user_id,
            knowledge_collection_ids=kb_ids,
            backend=backend,
        )

        # ------------------------------------------------------------------
        # Step 4: 创建 Trace 回调处理器
        # DBTraceHandler 实现了 LangChain 的 BaseCallbackHandler 接口，
        # 自动在 on_llm_start/end 和 on_tool_start/end 时将事件写入
        # trace_events 表，供前端监控看板展示。
        # ------------------------------------------------------------------
        trace_handler = DBTraceHandler()
        set_trace_context(
            tenant_id=int(tenant_id), user_id=int(user_id),
            thread_id=thread_id,
        )

        # ------------------------------------------------------------------
        # LangGraph 运行配置
        #   configurable: 传递给 checkpointer 的上下文（thread_id 用于状态隔离）
        #   callbacks:    LangChain 回调处理器列表（LangGraph 自动传播到所有节点）
        # ------------------------------------------------------------------
        config = {
            "configurable": {
                "thread_id": thread_id,      # 格式: {tenant_slug}:{user_id}:{uuid}
                "user_id": user_id,
                "tenant_id": tenant_id,
            },
            "callbacks": [trace_handler],
        }

        # 清理上轮不完整的 tool_calls（子Agent 超时导致请求中断，
        # checkpointer 只保存了 AIMessage(tool_calls) 而没有 ToolMessage）
        _cleanup_stale_checkpoint(self._checkpointer, thread_id)

        # ------------------------------------------------------------------
        # 安全围栏：输入防御纵深
        # chat.py 已做首道拦截（持久化前），这里兜底其他直接调用本方法的路径
        # 拦截 → error 事件并终止；脱敏 → 用脱敏文本继续
        # 围栏自身异常 → fail-open（可用性优先）
        # ------------------------------------------------------------------
        try:
            from app.core.guardrails.chain import GuardrailChain
            _g = GuardrailChain().check_input(user_message)
            if not _g.passed:
                logger.warning(f"Guardrail blocked input in orchestrator: {_g.reason[:200]}")
                yield f"data: {json.dumps({'type': 'error', 'message': f'[安全围栏] {_g.reason}'}, ensure_ascii=False)}\n\n"
                return
            if _g.modified_text and _g.modified_text != user_message:
                user_message = _g.modified_text
        except Exception as e:
            logger.warning(f"Guardrail check failed in orchestrator (fail-open): {e}")

        try:
            last_usage = None  # 收集最后一次 LLM 调用的 token 用量信息
            # task 工具 → 子代理名映射（tool_call_id → subagent_type）：
            # tool_start 以子代理名发射，tool_end 必须同名（前端按精确名
            # 匹配成对 tool_start/tool_end，deepagents 的 task ToolMessage
            # 其 name 为 "task"）
            task_calls: dict[str, str] = {}

            # ------------------------------------------------------------------
            # Step 5: 构建系统提示词
            # 包含全局规则 + Agent 自定义指令 + Skill 行为规则
            # ------------------------------------------------------------------
            system_prompt = self._build_system_prompt(agent_id, tenant_id, user_id=user_id)

            # ------------------------------------------------------------------
            # Step 6-7: 执行 LangGraph，双流迭代
            #
            # stream_mode=["messages", "updates"] 同时产出两个流：
            #   ("messages", (AIMessageChunk, metadata))
            #       LLM 逐 token 的文本增量 → 前端打字机式渲染
            #   ("updates", {node_name: {messages: [...]}})
            #       节点完成后完整状态 → 工具调用完整参数 + 用量元数据
            #
            # 示例迭代序列（一次带工具调用的对话）：
            #   messages: token, token, ... （第一轮 LLM 文本，通常为空）
            #   updates:  {"agent": AIMessage(tool_calls=[...])}  → tool_start
            #   updates:  {"tools": ToolMessage(...)}             → tool_end
            #   messages: token, token, ... （最终回复逐 token）
            #   updates:  {"agent": AIMessage(content=完整回复)}  → 收集用量
            #
            # 文本只从 messages 流发射（updates 里的完整回复不再重复发射），
            # 工具事件只从 updates 流发射（messages 流中的 tool_call_chunks 忽略）。
            # ------------------------------------------------------------------
            for stream_item in graph.stream(
                {"messages": [
                    SystemMessage(content=system_prompt),   # 含 Agent + Skill 规则
                    HumanMessage(content=user_message),     # 用户输入
                ]},
                config,
                stream_mode=["messages", "updates"],
            ):
                mode, payload = stream_item

                # ----------------------------------------------------------
                # messages 流：LLM 文本增量 → 逐 token 发射
                # ----------------------------------------------------------
                if mode == "messages":
                    chunk, _chunk_meta = payload
                    if hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        if isinstance(content, list):
                            text = "".join(
                                c.get("text", "") if isinstance(c, dict) else str(c)
                                for c in content
                            )
                        elif isinstance(content, str):
                            text = content
                        else:
                            text = str(content)
                        if text:
                            yield f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"
                    continue

                # ----------------------------------------------------------
                # updates 流：节点完整输出
                # 只处理 ToolMessage（tool_end）、tool_calls（tool_start）
                # 和 usage_metadata（用量），文本不再从这里发射
                # ----------------------------------------------------------
                for _node_name, node_output in payload.items():
                    # 中间件钩子节点（如 patch_tool_calls.before_agent、
                    # 子代理 task 的中间件）输出可能为 None，需跳过
                    messages = (node_output or {}).get("messages", [])
                    for msg in messages:
                        # --------------------------------------------------
                        # ToolMessage → 只发 tool_end，不发 token 事件
                        # --------------------------------------------------
                        if hasattr(msg, "type") and msg.type == "tool":
                            # task 工具的 ToolMessage：其 name 恒为 "task"，
                            # 须映射回 tool_start 已发射的子代理名
                            tool_name = task_calls.get(
                                getattr(msg, "tool_call_id", None),
                                getattr(msg, "name", "unknown"),
                            )
                            tool_output = str(msg.content) if hasattr(msg, "content") else ""
                            yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name, 'output': tool_output[:500]}, ensure_ascii=False)}\n\n"
                            continue

                        # --------------------------------------------------
                        # LLM 请求调用工具 → tool_start 事件
                        # tool_calls 可能是 dict (LangChain 新版本) 或对象 (旧版本)
                        # 每个 tool_call 包含 name（工具名）和 args（参数）
                        # --------------------------------------------------
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                if isinstance(tc, dict):
                                    tool_name = tc.get("name", "")
                                    tool_args = tc.get("args", {})
                                    tc_id = tc.get("id", "")
                                else:
                                    tool_name = getattr(tc, "name", "unknown")
                                    tool_args = getattr(tc, "args", {})
                                    tc_id = getattr(tc, "id", "")
                                if not tool_name:
                                    continue
                                # deepagents 默认工具中文别名（前端展示用）
                                display_name = TOOL_DISPLAY_NAMES.get(tool_name)
                                # task 工具 → 以子代理类型名发射
                                # （与旧协议 sub_agent_*/skill_* 工具名一致，
                                # 前端/回归测试按此名匹配；task 本体工具名
                                # 是 "task"，调用参数 subagent_type 才是身份）
                                if tool_name == "task":
                                    sub_type = (
                                        tool_args.get("subagent_type")
                                        if isinstance(tool_args, dict) else None
                                    ) or tool_name
                                    task_calls[tc_id] = sub_type
                                    tool_name = sub_type
                                event = {"type": "tool_start", "tool": tool_name,
                                         "input": json.dumps(tool_args, ensure_ascii=False)}
                                if display_name:
                                    event["display_name"] = display_name
                                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                        # (tool_end 事件已在 ToolMessage 入口统一处理)

                        # --------------------------------------------------
                        # 收集 token 用量（来自 LLM 响应的 usage_metadata）
                        # DeepSeek/OpenAI 的 AIMessage 自动携带 usage_metadata:
                        #   {"input_tokens": 523, "output_tokens": 555, "total_tokens": 1078}
                        # 用最后一次的用量覆盖（多轮 LLM 调用时累积的是全部的）
                        # 注意：这里取最后一次，因为每轮 graph 迭代可能有多轮 LLM 调用
                        # --------------------------------------------------
                        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                            input_tokens = msg.usage_metadata.get("input_tokens", 0)
                            output_tokens = msg.usage_metadata.get("output_tokens", 0)
                            if input_tokens or output_tokens:
                                last_usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}

            # ------------------------------------------------------------------
            # Step 8: 发送 done 事件，附带 token 用量 + trace_id
            # chat.py 的 generate() 会解析 usage 并调用 CostTracker.record()
            # trace_id 供前端展示本次对话的遥测标识（可跳转监控页溯源）
            # ------------------------------------------------------------------
            done_data: dict = {"type": "done"}
            if last_usage:
                done_data["usage"] = last_usage
            try:
                from app.core.monitoring.trace_callback import get_trace_id
                trace_id = get_trace_id()
                if trace_id:
                    done_data["trace_id"] = trace_id
            except Exception:
                pass
            yield f"data: {json.dumps(done_data)}\n\n"

        except Exception as e:
            logger.exception(f"Agent stream error for thread {thread_id}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    # =========================================================================
    # 遗留方法（备用 / 向后兼容）
    # =========================================================================

    def _format_event(self, event: dict) -> str | None:
        """
        [备用] 将 LangGraph astream_events() 的事件格式化为 SSE。

        注意：当前 stream_chat() 使用 stream_mode="updates"，
        此方法仅在切换到 astream_events() 时使用。
        保留此方法以便未来可能需要逐 chunk 流式输出。
        """
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                content = chunk.content
                if isinstance(content, list):
                    text = "".join(
                        c.get("text", "") if isinstance(c, dict) else str(c)
                        for c in content
                    )
                else:
                    text = str(content)
                if text:
                    return f"data: {json.dumps({'type': 'token', 'content': text}, ensure_ascii=False)}\n\n"

        elif kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            tool_input = event["data"].get("input", {})
            return f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name, 'input': str(tool_input)}, ensure_ascii=False)}\n\n"

        elif kind == "on_tool_end":
            tool_name = event.get("name", "unknown")
            output = str(event["data"].get("output", ""))
            return f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name, 'output': output}, ensure_ascii=False)}\n\n"

        return None

    def delete_thread_checkpoint(self, thread_id: str) -> bool:
        """
        清理指定线程在 PostgresSaver 中的检查点数据。

        采用 psycopg3 直连（非连接池）执行 DELETE，因为 CHECKPOINT 表上
        CREATE INDEX CONCURRENTLY 可能使连接池中的连接处于事务状态，
        导致 autocommit 设置不生效。

        Args:
            thread_id: 完整线程 ID（格式 {tenant_slug}:{user_id}:{uuid}）

        Returns:
            True 如果清理了数据，False 如果无数据可清理
        """
        if not self._checkpointer:
            return False

        deleted = _delete_checkpoint_by_tid(self._checkpointer, thread_id)
        if deleted > 0:
            logger.info(
                f"Cleaned up {deleted} checkpoint rows for thread {thread_id}"
            )
        return deleted > 0

    def get_thread_state(self, thread_id: str) -> dict | None:
        """
        从 checkpointer 读取对话历史状态。

        优先从 PostgresSaver 直接读取（不依赖图实例），
        降级方案是从所有缓存的图实例中查询。

        Args:
            thread_id: 完整的线程 ID（格式: {tenant_slug}:{user_id}:{uuid}）

        Returns:
            {"thread_id": ..., "message_count": N,
             "messages": [{"role": "user|assistant|system", "content": "..."}, ...]}
        """
        config = {"configurable": {"thread_id": thread_id}}

        # 方案 A：直接从 checkpointer 的 PostgreSQL 连接读取
        # 不依赖缓存的图实例，即使进程重启也能读回历史
        if self._checkpointer:
            try:
                state = self._checkpointer.get_tuple(config)
                if state and state.checkpoint:
                    cp = state.checkpoint
                    messages = cp.get("channel_values", {}).get("messages", [])
                    if messages:
                        return self._format_messages(thread_id, messages)
            except Exception:
                pass

        # 方案 B：降级到图实例的 get_state()
        # 遍历 DeepAgentFactory 缓存的所有图，用第一个能找到状态的
        factory = self._deep_factory
        if factory:
            for graph in factory._cache.values():
                try:
                    state = graph.get_state(config)
                    if state and state.values:
                        messages = state.values.get("messages", [])
                        if messages:
                            return self._format_messages(thread_id, messages)
                except Exception:
                    continue
        return None

    def _format_messages(self, thread_id: str, messages: list) -> dict:
        """
        将 LangChain 消息列表转换为前端友好的 JSON 格式。

        LangChain 消息类型映射到 role：
          HumanMessage    → "user"
          AIMessage       → "assistant"
          SystemMessage   → "system"
          其他            → 类型名的字符串形式
        """
        return {
            "thread_id": thread_id,
            # 与 chat_messages 表口径一致：
            #   - HumanMessage 全算
            #   - AIMessage 仅算有非空文本内容的（纯工具调用的 AIMessage 内容为空，
            #     DB 只持久化最终回复，不持久化中间的工具调用消息）
            #   - ToolMessage/SystemMessage 不算
            "message_count": sum(
                1 for m in messages
                if isinstance(m, HumanMessage)
                or (
                    isinstance(m, AIMessage)
                    and isinstance(m.content, str)
                    and m.content.strip()
                )
            ),
            "messages": [
                {
                    "role": (
                        "user" if isinstance(m, HumanMessage)
                        else "assistant" if isinstance(m, AIMessage)
                        else "system" if hasattr(m, "type") and m.type == "system"
                        else str(type(m).__name__)
                    ),
                    "content": (m.content if isinstance(m.content, str) else str(m.content)),
                }
                for m in messages
            ],
        }
