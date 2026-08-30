"""DeepAgentFactory — 按 Agent 配置组装 deepagents 编译图

职责：读 AgentConfig / SubAgentDefinition / SkillConfig / ModelProvider，
组装 create_deep_agent 全部参数；按指纹缓存编译图。

与 brief 草案的偏差（见 task-3-report）：
1. build() 增加可选 tools 参数 —— orchestrator._resolve_tools 的返回
   （DEFAULT_TOOLS 过滤 + MCP 工具）整体并入此处作为最终 EAP 工具集；
2. 缓存键含 tenant_id + thread_id —— deepagents 的执行后端（线程工作目录）
   在编译期即烘焙进 FilesystemMiddleware（无运行时覆盖），跨线程/跨租户
   复用图会串工作区；
3. memory 传沙箱相对路径 ["/memory/AGENTS.md"] 而非宿主绝对路径
   （brief 的 str 写法违反 list[str] 签名，且绝对路径在虚拟模式下会
   被错误映射到工作区内的同名目录）；该路径与 deepagents 内置 memory
   工具读写路径一致；
4. 子代理名 sub_agent_{name}（与旧协议工具名一致，前端成对匹配依赖）；
   sub.tools 从 DB 工具名映射为 DEFAULT_TOOLS 对象（字符串名会
   crash 图构建），映射为空时省略 tools 键 → 子代理继承主代理工具；
5. interrupt_on 暂由 INTERRUPT_ENABLED 门控（Task 5 激活）。
"""
import hashlib
import logging

from deepagents import create_deep_agent

from app.models.agent_config import AgentConfig
from app.models.skill_config import SkillConfig
from app.models.sub_agent import SubAgentDefinition
from app.core.agent.backends import build_backend
from app.core.agent.tools import DEFAULT_TOOLS

logger = logging.getLogger(__name__)

# deepagents 默认工具中文别名（tool_start 事件 display_name 字段）
TOOL_DISPLAY_NAMES = {
    "write_todos": "任务规划",
    "ls": "列出文件",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "edit_file": "编辑文件",
    "glob": "查找文件",
    "grep": "内容搜索",
    "execute": "代码执行",
    "task": "子代理调度",
}

# permission_mode → interrupt_on（HITL，Task 5 激活）
HITL_TOOLS = ["write_file", "edit_file", "execute"]
# Task 3 保持关闭：interrupt_on 一旦启用，execute/write/edit 会在没有
# resume 通道（HITL API 未实现）的情况下永久挂起，破坏生产代码执行。
# Task 5 实现 HITL API 后置为 True。
INTERRUPT_ENABLED = False

# 记忆文件在沙箱内的统一路径：经后端映射为
#   local     → {thread_workspace}/memory/AGENTS.md
#   container → {root_dir 挂载 /workspace}/memory/AGENTS.md
# 与 deepagents 内置 memory 工具的读写路径一致（保存后可被再次加载）。
MEMORY_FILE = "/memory/AGENTS.md"


class DeepAgentFactory:
    def __init__(self):
        self._cache: dict[str, object] = {}

    def build(self, tenant_id: str, agent_id: int | None, user_id: str,
              provider_config: dict, thread_id: str,
              tools: list | None = None) -> tuple[object, str]:
        """组装 deepagent 编译图。返回 (graph, cache_key)。

        tools: orchestrator._resolve_tools 的返回（DEFAULT_TOOLS 过滤 +
        MCP 工具），作为最终 EAP 工具集；None 时退化为按 tools_config
        从 DEFAULT_TOOLS 自过滤。deepagents 默认工具（ls/read_file/
        write_file/edit_file/glob/grep/execute/task/write_todos）由
        create_deep_agent 自动追加，不在此列。
        """
        agent = None
        skills, subagents, interrupt_on, backend_mode = [], [], [], "local"
        tool_names = None

        if agent_id:
            agent = AgentConfig.query.filter_by(
                id=agent_id, tenant_id=int(tenant_id)).first()
        if agent:
            # tools_config：自有工具按配置过滤（code_execution 名字 → execute 开关）
            tool_names = set(agent.tools_config or [])
            backend_mode = (agent.backend or "local")
            interrupt_on = (
                HITL_TOOLS
                if INTERRUPT_ENABLED and (agent.permission_mode or "default") == "default"
                else []
            )

            # prompt 模式 skill → deepagents skills 目录（渐进披露）
            # 最佳努力：宿主绝对路径在沙箱内不存在时跳过并告警，不影响对话
            for s in SkillConfig.query.filter(
                    SkillConfig.tenant_id == int(tenant_id),
                    SkillConfig.name.in_(agent.skills or []),
                    SkillConfig.is_active == True,
                    SkillConfig.mode == "prompt").all():
                if s.file_path:
                    skills.append(s.file_path)

            # agent 模式 skill + 子 agent → subagents dict
            for s in SkillConfig.query.filter(
                    SkillConfig.tenant_id == int(tenant_id),
                    SkillConfig.name.in_(agent.skills or []),
                    SkillConfig.is_active == True,
                    SkillConfig.mode == "agent").all():
                subagents.append(self._skill_subagent(s))
            for sub in SubAgentDefinition.query.filter_by(
                    tenant_id=int(tenant_id), parent_agent_id=agent_id, is_active=True).all():
                subagents.append(self._db_subagent(sub, tenant_id))

        # 自有工具集（含子代理可继承的常用工具；execute 由 deepagents 内置提供，
        # 当 tools_config 未勾选 code_execution 时排除 deepagents 默认工具中的 execute）
        if tools is None:
            tools = self._filter_own_tools(tool_names)

        backend = build_backend(backend_mode, str(tenant_id), str(user_id), thread_id)

        cache_key = self._cache_key(tenant_id, agent_id, provider_config,
                                    backend_mode, subagents, interrupt_on,
                                    thread_id, tools)
        if cache_key in self._cache:
            return self._cache[cache_key], cache_key

        graph = create_deep_agent(
            model=provider_config["_llm"],
            tools=tools,
            subagents=subagents or None,
            skills=skills or None,
            backend=backend,
            memory=[MEMORY_FILE],   # 每线程目录内持久化用户记忆文件
            interrupt_on=interrupt_on or None,
            checkpointer=provider_config["_checkpointer"],
        )
        self._cache[cache_key] = graph
        return graph, cache_key

    # ---------- 内部 ----------
    def _skill_subagent(self, s: SkillConfig) -> dict:
        prompt = s.get_prompt()
        return {
            "name": f"skill_{s.name}",
            "description": f"技能「{s.name}」: {s.description or ''}",
            "system_prompt": prompt,
        }

    def _db_subagent(self, sub: SubAgentDefinition, tenant_id: str) -> dict:
        spec = {
            # 与旧协议 sub_agent_{name} 工具名一致：task 工具调用名
            # 映射为 SSE tool_start/tool_end 的工具名，前端按精确名成对匹配
            "name": f"sub_agent_{sub.name}",
            "description": f"子代理「{sub.name}」: {(sub.role_prompt or '')[:100]}",
            "system_prompt": sub.role_prompt,
        }
        # DB 存工具名（str），deepagents 需要工具对象 —— 映射到 DEFAULT_TOOLS；
        # 映射为空时省略 tools 键 → 子代理继承主代理工具（deepagents
        # SubAgent 文档语义："If not specified, inherits tools from the main agent"）
        sub_tools = self._map_sub_tools(sub.tools or [])
        if sub_tools:
            spec["tools"] = sub_tools
        # 子代理独立模型：Task 4 增加 model_provider_id 列后才启用；
        # 当前模型无此列，getattr 兜底为 None（不传 model 键 → 继承主代理模型）
        sub_mp_id = getattr(sub, "model_provider_id", None)
        if sub_mp_id:
            from app.models.model_provider import ModelProvider
            mp = ModelProvider.query.filter_by(
                id=sub_mp_id, tenant_id=int(tenant_id)).first()
            if mp:
                spec["model"] = self._build_sub_llm(mp)
        return spec

    def _map_sub_tools(self, names: list) -> list:
        name_set = set(names)
        return [t for t in DEFAULT_TOOLS if t.name in name_set]

    def _build_sub_llm(self, mp) -> object:
        from app.core.agent.orchestrator import AgentOrchestrator
        return AgentOrchestrator._build_llm(AgentOrchestrator(), {
            "provider": mp.provider, "model_name": mp.model_name,
            "api_key": mp.api_key, "api_base": mp.api_base,
        })

    def _filter_own_tools(self, tool_names: set | None) -> list:
        """自有工具过滤；deepagents 默认工具（含 execute）由其自身提供，
        code_execution 配置名映射为 execute 启用开关，见 orchestrator 组装处。"""
        if tool_names is None:
            return list(DEFAULT_TOOLS)
        return [t for t in DEFAULT_TOOLS if t.name in tool_names]

    def _cache_key(self, tenant_id, agent_id, provider_config, backend_mode,
                   subagents, interrupt_on, thread_id, final_tools) -> str:
        endpoint = hashlib.sha256(
            f"{provider_config.get('api_base', '')}|{provider_config.get('api_key', '')}".encode()
        ).hexdigest()[:8]
        parts = [
            provider_config["provider"], provider_config["model_name"],
            ",".join(sorted(t.name for t in final_tools)),
            backend_mode,
            ",".join(sorted(s["name"] for s in subagents)),
            ",".join(interrupt_on or []),
            endpoint,
            # 线程维度：执行后端（线程工作目录）编译期烘焙进中间件，
            # 跨线程复用图会串工作区
            thread_id,
            # 租户维度：不同租户的相同 agent_id 配置各异，图不可跨租户共享
            str(tenant_id),
        ]
        return ":".join(parts)
