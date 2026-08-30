"""local 后端 — deepagents FilesystemBackend + 线程隔离目录"""
import os
from deepagents.backends.filesystem import FilesystemBackend


def build_filesystem_backend(root: str) -> FilesystemBackend:
    os.makedirs(root, exist_ok=True)
    return FilesystemBackend(root_dir=root)
