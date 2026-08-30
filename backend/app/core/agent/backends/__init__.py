"""执行后端工厂 — local(FilesystemBackend) / container(DockerBackend)"""
from app.core.agent.backends.docker_backend import DockerBackend
from app.core.agent.backends.filesystem_backend import build_filesystem_backend

WORKSPACE_BASE = "/home/wangyan/deploy/eap/agent_workspaces"


class BackendUnavailableError(Exception):
    """backend 构建失败（fail-closed，调用方转为明确 error 事件）"""


def build_workspace_root(tenant_id: str, user_id: str, thread_id: str) -> str:
    """每线程独立工作目录：租户/用户/线程三级隔离"""
    return f"{WORKSPACE_BASE}/{tenant_id}/{user_id}/{thread_id}"


def build_backend(mode: str, tenant_id: str, user_id: str, thread_id: str):
    """按 Agent 配置的执行后端构建实例。

    mode: "local" | "container"
    失败（Docker 不可用/镜像缺失/非法 mode）抛 BackendUnavailableError，
    调用方必须 fail-closed —— 绝不回退宿主机执行。
    """
    root = build_workspace_root(tenant_id, user_id, thread_id)
    if mode == "local":
        return build_filesystem_backend(root)
    if mode == "container":
        try:
            return DockerBackend(root_dir=root)
        except Exception as e:
            raise BackendUnavailableError(f"容器后端不可用: {e}") from e
    raise BackendUnavailableError(f"未知执行后端: {mode}")
