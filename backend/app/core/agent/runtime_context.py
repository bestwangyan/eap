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
    返回 Agent 配置的执行后端: "local"（默认，宿主机受限执行）| "container"（预留）。

    预留接口：后续实现 Docker 容器沙箱时，code_execution 等工具通过本函数
    感知执行环境，无需再改编排器调用链。
    """
    return _backend.get()
