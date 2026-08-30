"""container 后端 — 一次性 Docker 容器沙箱（SandboxBackendProtocol）

沙箱参数：--network none --memory 256m --cpus 1 --pids-limit 64 --cap-drop ALL
文件持久化：宿主 root_dir 挂载到容器 /workspace
镜像：python:3.12-slim（部署时预热）

实现说明（与 brief 草案的偏差见 task-2-report）：
继承 deepagents.backends.sandbox.BaseSandbox —— 其 ls/read/write/edit/
grep/glob/delete 均以 python3 脚本经 execute() 在容器内执行（本镜像自带
python3），并返回协议规定的结构化结果（LsResult/ReadResult/...）。本类
只需实现四个原语：execute / upload_files / download_files / id。
"""
import os
import re
import subprocess
import uuid
from pathlib import Path

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

IMAGE = "python:3.12-slim"
DEFAULT_EXECUTE_TIMEOUT = 120
"""默认命令超时（秒）。对齐 deepagents LocalShellBackend 的默认值；
brief 草案的 10s 对 pip install 等合法长命令过短，故取实测生态默认。"""
WORKSPACE_MOUNT = "/workspace"
"""宿主 root_dir 在容器内的挂载点。"""
MEMORY_ROOT = "/memory"
"""平台记忆文件根（DeepAgentFactory 统一传入 "/memory/AGENTS.md"）。
本地/无 execute 变体（FilesystemBackend virtual_mode）天然映射到
root_dir/memory/；完整容器变体在此显式映射到同一宿主落点
（容器内挂载视角为 /workspace/memory/AGENTS.md）。"""


def _map_to_host(root_dir: Path, sandbox_path: str) -> Path | None:
    """沙箱绝对路径 → 宿主 root_dir 内路径。

    接受两类前缀：
      /workspace/* → root_dir/*（挂载视角：/workspace 即 root_dir）
      /memory/*    → root_dir/memory/*（平台记忆文件；MemoryMiddleware
                      download_files 读入，write_file 工具经 upload 落盘）
    其余路径返回 None（fail-closed，拒绝宿主机逃逸）。
    resolve() 做词法归一（阻断 `..` 穿越）并解析已存在父目录的符号链接，
    最终必须仍位于 root_dir 之内，否则返回 None。
    """
    p = Path(sandbox_path).resolve()
    root = root_dir.resolve()
    try:
        rel = p.relative_to(Path(WORKSPACE_MOUNT).resolve())
    except ValueError:
        try:
            rel = p.relative_to(Path(MEMORY_ROOT).resolve())
        except ValueError:
            return None
        rel = Path("memory") / rel   # /memory/x → root_dir/memory/x
    host = (root / rel).resolve()
    try:
        host.relative_to(root)
    except ValueError:
        return None
    return host


class DockerBackend(BaseSandbox):
    """一次性容器沙箱：每次 execute 起一个 --rm 容器，文件经挂载持久化。"""

    def __init__(self, root_dir: str):
        # 构建时校验 Docker 可用 + 镜像存在（fail-closed 的第一道闸）
        chk = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=5,
        )
        if chk.returncode != 0:
            raise RuntimeError(f"Docker 不可用: {chk.stderr.strip()}")
        img = subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            capture_output=True, text=True, timeout=10,
        )
        if img.returncode != 0:
            raise RuntimeError(f"镜像 {IMAGE} 缺失，请先 docker pull")
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def id(self) -> str:
        return f"docker:{self.root_dir}"

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """容器内执行任意 shell 命令（cwd=/workspace），输出/退出码结构同
        LocalShellBackend 约定，供 LLM 直接消费。"""
        if not command or not isinstance(command, str):
            return ExecuteResponse(
                output="Error: Command must be a non-empty string.",
                exit_code=1,
                truncated=False,
            )
        effective_timeout = timeout if timeout is not None else DEFAULT_EXECUTE_TIMEOUT
        if effective_timeout <= 0:
            msg = f"timeout must be positive, got {effective_timeout}"
            raise ValueError(msg)

        # 每次执行用唯一 cidfile 记录容器 ID。cidfile 写到 root_dir **之外**
        # （root_dir.parent）—— root_dir 整体 bind-mount 为容器 /workspace，
        # 放挂载内会被容器内命令删除/篡改（如 `rm /workspace/.eap-*`），
        # 导致超时挂起时无法凭它精确 `docker rm -f` 强杀容器而泄漏（终审
        # B3 修复）。uuid 命名防并发执行互相覆盖。--rm 只在容器进程自行
        # 退出后清理，挂起命令（如 `sleep infinity`，LLM 提示注入可构造）
        # 否则会永久泄漏容器（每个 256m）。
        cidfile = self.root_dir.parent / f".eap-cid-{uuid.uuid4().hex}"
        # --mount 而非 -v：线程工作目录含平台线程 id（`{tenant_slug}:{user_id}:{uuid}`，
        # 如 default:1:1bb19970-...），-v 的 `host:container` 语法会按冒号切分 →
        # "too many colons"；--mount 按逗号切分 key=value，src 中的冒号安全。
        # --cap-drop ALL（终审硬化）：容器只需文件 IO（挂载写入）与 python3，
        # 剥离全部 Linux capability 收窄注入面。
        cmd = [
            "docker", "run", "--rm",
            "--cidfile", str(cidfile),
            "--network", "none",
            "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
            "--cap-drop", "ALL",
            "--mount", f"type=bind,src={self.root_dir},dst={WORKSPACE_MOUNT}",
            "-w", WORKSPACE_MOUNT,
            IMAGE, "sh", "-c", command,
        ]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True, text=True,
                stdin=subprocess.DEVNULL,  # 防止命令读 stdin 挂起
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            self._rm_stuck_container(cidfile)
            if timeout is not None:
                msg = f"Error: Command timed out after {effective_timeout} seconds (custom timeout). The command may be stuck or require more time."
            else:
                msg = f"Error: Command timed out after {effective_timeout} seconds. For long-running commands, re-run using the timeout parameter."
            return ExecuteResponse(output=msg, exit_code=124, truncated=False)
        except Exception as e:  # noqa: BLE001
            return ExecuteResponse(
                output=f"Error executing command ({type(e).__name__}): {e}",
                exit_code=1,
                truncated=False,
            )
        finally:
            cidfile.unlink(missing_ok=True)

        out_parts = []
        if r.stdout:
            out_parts.append(r.stdout)
        if r.stderr:
            stderr_lines = r.stderr.strip().split("\n")
            out_parts.extend(f"[stderr] {line}" for line in stderr_lines)
        output = "\n".join(out_parts) if out_parts else "<no output>"
        if r.returncode != 0:
            output = f"{output.rstrip()}\n\nExit code: {r.returncode}"
        return ExecuteResponse(output=output, exit_code=r.returncode, truncated=False)

    def _rm_stuck_container(self, cidfile: Path) -> None:
        """超时兜底：`docker rm -f` 强杀仍挂起的容器，防止资源泄漏。

        仅按 cidfile 内容精确删除本命令对应的容器：容器 ID 必须是 docker
        写入的完整 64 位 hex ID（不信任任何 shell 拼接）。cidfile 位于
        root_dir 之外（终审 B3 修复：写挂载外，容器内命令无法触碰），
        内容不合规时仍拒绝删除（fail-closed，绝不误删其他容器）。删除
        失败时静默放弃 —— 主路径已返回超时错误，后续 --rm 语义不受影响。
        """
        try:
            cid = cidfile.read_text().strip()
        except OSError:
            return
        if not re.fullmatch(r"[0-9a-f]{64}", cid):
            return
        try:
            subprocess.run(
                ["docker", "rm", "-f", cid],
                capture_output=True, text=True, timeout=30,
            )
        except Exception:  # noqa: BLE001
            return

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """写入宿主 root_dir（经挂载进入容器 /workspace 视角）。

        仅接受 /workspace 前缀的绝对路径；越界路径返回 invalid_path，
        绝不写入 root_dir 之外（防宿主机逃逸）。
        """
        responses = []
        for path, content in files:
            host = _map_to_host(self.root_dir, path)
            if host is None:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                host.parent.mkdir(parents=True, exist_ok=True)
                host.write_bytes(content)
                responses.append(FileUploadResponse(path=path))
            except OSError as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """从宿主 root_dir（/workspace 视角）读取文件字节。"""
        responses = []
        for path in paths:
            host = _map_to_host(self.root_dir, path)
            if host is None:
                responses.append(FileDownloadResponse(path=path, error="invalid_path"))
                continue
            try:
                content = host.read_bytes()
                responses.append(FileDownloadResponse(path=path, content=content))
            except FileNotFoundError:
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
            except OSError as e:
                responses.append(FileDownloadResponse(path=path, error=str(e)))
        return responses


class DockerBackendNoShell(FilesystemBackend):
    """container 模式的"无 execute"变体（code_execution 启用开关 = 关）。

    review Important 1 修复：deepagents 0.7.11 的默认工具不可按名字裁剪，
    execute 只在 backend 实现 SandboxBackendProtocol 时注入模型请求
    （middleware 的 supports_execution() → _filter_unsupported_tools_and_
    apply_prompt 会把 execute 从模型 schema 中剔除）。因此开关改为
    backend 变体控制：

    - 本类仅实现 BackendProtocol（文件操作），不实现 SandboxBackendProtocol
      —— 不继承 BaseSandbox、无 execute() 方法 → supports_execution()
      isinstance 检查为 False → execute 对模型不可见/不可调；
    - 文件操作直接复用 deepagents FilesystemBackend 的宿主侧纯 Python
      实现（virtual_mode=True，路径语义与沙箱一致）：root_dir 挂载为容器
      /workspace，宿主视角与容器视角完全等价，无需任何 shell；
    - delete 在 FilesystemBackend 中已实现 → 不被 _supports_delete 过滤。

    与完整 DockerBackend 的唯一差异即缺失 execute（无容器拉起、无 shell）；
    文件能力（ls/read/write/edit/delete/glob/grep/upload/download）与
    memory 语义（/memory/AGENTS.md → root_dir/memory/AGENTS.md）保持一致。
    """

    def __init__(self, root_dir: str):
        os.makedirs(root_dir, exist_ok=True)
        super().__init__(root_dir=root_dir)  # virtual_mode=True（默认）

    @property
    def id(self) -> str:
        return f"docker-noshell:{self.cwd}"
