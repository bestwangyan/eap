"""Runtime context for Agent tools — propagates tenant/user/agent info via contextvars"""
from contextvars import ContextVar

_tenant_id: ContextVar[str] = ContextVar("agent_tenant_id", default="")
_user_id: ContextVar[str] = ContextVar("agent_user_id", default="")
_tenant_slug: ContextVar[str] = ContextVar("agent_tenant_slug", default="")
_knowledge_collection_ids: ContextVar[list] = ContextVar("agent_kb_collections", default=[])
_backend: ContextVar[str] = ContextVar("agent_backend", default="local")


def set_runtime_context(
    tenant_id: str,
    user_id: str,
    tenant_slug: str = "",
    knowledge_collection_ids: list | None = None,
    backend: str | None = None,
):
    _tenant_id.set(str(tenant_id))
    _user_id.set(str(user_id))
    _tenant_slug.set(tenant_slug)
    if knowledge_collection_ids is not None:
        _knowledge_collection_ids.set(knowledge_collection_ids)
    if backend is not None:
        _backend.set(backend)


def get_tenant_id() -> str:
    try:
        from flask import g
        return str(g.tenant_id)
    except (RuntimeError, AttributeError):
        pass
    return _tenant_id.get()


def get_user_id() -> str:
    try:
        from flask import g
        return str(g.user_id)
    except (RuntimeError, AttributeError):
        pass
    return _user_id.get()


def get_knowledge_collection_ids() -> list:
    """返回 Agent 配置中限定使用的知识库集合 ID 列表。空列表 = 不限制。"""
    return list(_knowledge_collection_ids.get())


def get_backend() -> str:
    """
    返回 Agent 配置的执行后端: "local" | "container"。

    Docker 容器沙箱已实现（backends/docker_backend.py，--cap-drop ALL 一次性
    容器），后端在编译期烘焙进 deepagents 图（deep_agent_factory.build →
    build_backend）；本函数供工具侧感知执行环境。
    """
    return _backend.get()
