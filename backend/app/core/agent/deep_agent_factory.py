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
from collections import OrderedDict

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
    "delete": "删除文件",
    "glob": "查找文件",
    "grep": "内容搜索",
    "execute": "代码执行",
    "task": "子代理调度",
}

# permission_mode → interrupt_on（HITL）
# HITL 工具集：文件写入/编辑 + 代码执行（读取类工具不打断）
HITL_TOOLS = ["write_file", "edit_file", "execute"]
# Task 3 保持关闭（无 resume 通道会永久挂起）；Task 5 实现 HITL API 后启用
INTERRUPT_ENABLED = True

# 记忆文件在沙箱内的统一路径：经后端映射为
#   local     → {thread_workspace}/memory/AGENTS.md
#   container → {root_dir 挂载 /workspace}/memory/AGENTS.md
#   container(无execute) → {root_dir}/memory/AGENTS.md（virtual_mode 映射）
# 与 deepagents 内置 memory 工具的读写路径一致（保存后可被再次加载）。
MEMORY_FILE = "/memory/AGENTS.md"

# 编译图缓存上限：缓存键含 thread_id（执行后端线程工作目录编译期烘焙），
# 每线程一条。maxsize=200 的 LRU 兜底防止长期运行无界膨胀
# （review Important 3 修复）；线程删除路径另有精确 evict()。
CACHE_MAXSIZE = 200


class DeepAgentFactory:
    def __init__(self):
        # OrderedDict 实现 LRU：命中 move_to_end，超限 popitem(last=False)
        self._cache: OrderedDict[str, object] = OrderedDict()
        # thread_id → 其全部 cache_key 的反向索引（evict 精确淘汰，无需
        # 子串匹配；LRU 淘汰时同步清理）
        self._thread_keys: dict[str, set[str]] = {}

    def evict(self, thread_id: str) -> None:
        """线程删除时精确淘汰该线程的全部编译图（按 cache_key 中 thread_id 段）。

        orchestrator.delete_thread_checkpoint 路径调用；LRU 淘汰之外的另一条
        释放通道，让被删线程的工作区目录与检查点尽快一起回收。
        """
        keys = self._thread_keys.pop(thread_id, None)
        if not keys:
            return
        for key in keys:
            self._cache.pop(key, None)
        logger.info("Evicted %d cached graph(s) for thread %s", len(keys), thread_id)

    def iter_graphs(self) -> list:
        """遍历当前缓存的全部编译图（get_thread_state 方案 B 降级查询用）。"""
        return list(self._cache.values())

    def build(self, tenant_id: str, agent_id: int | None, user_id: str,
              provider_config: dict, thread_id: str,
              tools: list | None = None) -> tuple[object, str]:
        """组装 deepagent 编译图。返回 (graph, cache_key)。

        tools: orchestrator._resolve_tools 的返回（DEFAULT_TOOLS 过滤 +
        MCP 工具），作为最终 EAP 工具集；None 时退化为按 tools_config
        从 DEFAULT_TOOLS 自过滤。deepagents 默认文件工具（ls/read_file/
        write_file/edit_file/glob/grep/delete/task/write_todos）由
        create_deep_agent 自动追加，不在此列；execute 由 backend 变体
        控制（tools_config 含 code_execution → 完整 DockerBackend，
        否则 DockerBackendNoShell → 模型请求无 execute）。

        能力限制（终审 B2）：deepagents 0.7.11 的默认文件工具**恒启用、
        不可按名裁剪** —— tools_config 勾选仅对自有工具与 code_execution
        （→execute 开关）生效；前端资源列表对默认工具作禁用态展示
        （builtin 标记 + "始终启用"提示）。
        """
        agent = None
        skills, subagents, interrupt_on, backend_mode = [], [], [], "local"
        tool_names = None
        execute_enabled = True

        if agent_id:
            agent = AgentConfig.query.filter_by(
                id=agent_id, tenant_id=int(tenant_id)).first()
        if agent:
            # tools_config：自有工具按配置过滤；
            # code_execution 名字 → execute 启用开关（review Important 1）：
            #   tools_config 含 "code_execution" → 完整 DockerBackend（有 execute）
            #   不含 → DockerBackendNoShell（不实现 SandboxBackendProtocol，
            #   deepagents 从模型请求过滤 execute）
            tool_names = set(agent.tools_config or [])
            execute_enabled = "code_execution" in tool_names
            backend_mode = (agent.backend or "local")
            # interrupt_on 必须是 dict {tool: True}（deepagents 0.7.11 的
            # _merge_fs_interrupt_on 对 user_interrupt_on 执行 dict.update，
            # 传 list 会 TypeError；True = 该工具全部决策允许
            # [approve/edit/reject/respond]）。
            # permission_mode == "default" → HITL 全开；
            # acceptEdits/dontAsk（自行确认/不询问）→ 全部放行（None）
            if INTERRUPT_ENABLED and (agent.permission_mode or "default") == "default":
                interrupt_on = {t: True for t in HITL_TOOLS}
            else:
                interrupt_on = None

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

        # 自有工具集（含子代理可继承的常用工具；execute 不在此列 —— 由
        # deepagents 按 backend 变体注入：execute_enabled 时完整 DockerBackend
        # 提供，否则 DockerBackendNoShell 使模型请求中无 execute）
        if tools is None:
            tools = self._filter_own_tools(tool_names)

        backend = build_backend(backend_mode, str(tenant_id), str(user_id),
                                thread_id, execute=execute_enabled)

        cache_key = self._cache_key(tenant_id, agent_id, provider_config,
                                    backend_mode, subagents, interrupt_on,
                                    thread_id, tools, execute_enabled)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)   # LRU 命中刷新
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
        # LRU 插入：超限淘汰最久未用（popitem(last=False)），并同步反向索引
        # （空集线程条目一并清理，防止线程 id 残留）
        self._cache[cache_key] = graph
        self._cache.move_to_end(cache_key)
        self._thread_keys.setdefault(thread_id, set()).add(cache_key)
        if len(self._cache) > CACHE_MAXSIZE:
            oldest_key, _ = self._cache.popitem(last=False)
            for t in list(self._thread_keys):
                ks = self._thread_keys[t]
                ks.discard(oldest_key)
                if not ks:
                    del self._thread_keys[t]
            logger.info("LRU evicted graph %s (cache size %d)", oldest_key, len(self._cache))
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
        """自有工具过滤（DEFAULT_TOOLS 子集，不含 execute）。"""
        if tool_names is None:
            return list(DEFAULT_TOOLS)
        return [t for t in DEFAULT_TOOLS if t.name in tool_names]

    def _cache_key(self, tenant_id, agent_id, provider_config, backend_mode,
                   subagents, interrupt_on, thread_id, final_tools,
                   execute_enabled) -> str:
        endpoint = hashlib.sha256(
            f"{provider_config.get('api_base', '')}|{provider_config.get('api_key', '')}".encode()
        ).hexdigest()[:8]
        parts = [
            provider_config["provider"], provider_config["model_name"],
            ",".join(sorted(t.name for t in final_tools)),
            backend_mode,
            # execute 开关维度：同配置下 DockerBackend / DockerBackendNoShell
            # 是两张不同的图，缓存键必须区分
            "exec" if execute_enabled else "noexec",
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
