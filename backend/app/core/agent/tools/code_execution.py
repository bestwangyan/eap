"""Sandboxed code execution tool"""
import subprocess
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 危险模块黑名单
_BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "requests",
    "importlib", "__builtins__", "builtins", "ctypes", "multiprocessing",
    "threading", "signal", "atexit", "posix", "nt", "pdb", "code",
    "compile", "exec", "eval", "open", "file",
}

_CODE_TIMEOUT = 10  # seconds


class CodeExecutionInput(BaseModel):
    code: str = Field(description="要执行的 Python 代码")
    language: str = Field(default="python", description="编程语言 (目前仅支持 python)")


def _execute_code(code: str, language: str = "python") -> str:
    """在受限子进程中执行代码"""
    if language != "python":
        return f"错误: 不支持的语言 '{language}'，目前仅支持 Python"

    # 快速安全检查 — 拒绝明显危险的代码
    code_lower = code.lower()
    for mod in _BLOCKED_MODULES:
        if f"import {mod}" in code_lower or f"from {mod}" in code_lower:
            if mod in ("open", "file", "exec", "eval", "compile"):
                return f"错误: 禁止使用 '{mod}' 函数"
            return f"错误: 禁止导入模块 '{mod}'（安全限制）"

    # 检查 __ 双下划线绕过
    if ("__" in code and ("import" in code_lower or "builtin" in code_lower)):
        return "错误: 检测到可疑的绕过尝试"

    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=_CODE_TIMEOUT,
            env={
                "PATH": "/usr/bin:/usr/local/bin",
                "HOME": "/tmp",
                "LANG": "C.UTF-8",
            },
        )

        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            if output:
                output += "\n"
            output += result.stderr.strip()

        if result.returncode != 0 and not output:
            output = f"进程退出码: {result.returncode}"

        return output or "(代码执行完成，无输出)"

    except subprocess.TimeoutExpired:
        return f"错误: 代码执行超时（{_CODE_TIMEOUT} 秒限制）"
    except Exception as e:
        return f"执行错误: {str(e)}"


code_execution_tool = StructuredTool.from_function(
    name="code_execution",
    description="在沙箱中执行 Python 代码。禁止导入危险模块和访问系统资源。超时 10 秒。",
    func=_execute_code,
    args_schema=CodeExecutionInput,
)
