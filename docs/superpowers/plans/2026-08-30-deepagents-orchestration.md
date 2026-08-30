# EAP 编排核心 deepagents 化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 deepagents 完全替换 EAP 手写 LangGraph 编排核心，启用 backend（本地/容器）、skills、subagents、memory、HITL 特性，对外 SSE 协议与前端零破坏。

**Architecture:** `DeepAgentFactory` 按 agent 配置组装 `create_deep_agent` 编译图（缓存复用）；执行后端双实现（FilesystemBackend / 自研 DockerBackend）；HITL 用 `interrupt_on` + 现有审批表；SSE 映射层适配 deepagents 输出。

**Tech Stack:** deepagents 0.7.11、langgraph 1.2.11、langchain-core ≥1.6.1、PostgreSQL checkpointer、React 18 + AntD。

**Spec:** `docs/superpowers/specs/2026-08-30-deepagents-orchestration-design.md`（分支 `deepagent`）

## Global Constraints

- deepagents==0.7.11；langchain-core>=1.6.1；langchain>=1.3.18；langchain-anthropic>=1.7.0
- SSE 协议向后兼容：token/tool_start/tool_end/done/error/thread_id 事件语义不变；新增 interrupt 事件与 tool_start 的 display_name 字段
- 服务器部署：双 venv + 符号链接（deploy-eap skill 陷阱 2）；每次任务完成后 `bash scripts/eap_full_test.sh` 全量回归（凭据在 scripts/.test.env）
- 安全：container backend 构建失败必须 fail-closed（error 事件），不得回退宿主机执行
- 分支：所有提交在 `deepagent` 分支

---

### Task 1: 依赖安装 + deepagents 冒烟验证（spike，锁定未知 API 形状）

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/scripts/spike_deepagents.py`（服务器冒烟脚本，实施后删除）
- Test: 冒烟输出为准（无 pytest，本项目测试模式为部署 + SSE 实测）

**Interfaces:**
- Consumes: 无
- Produces: 记录在案的 `SandboxBackendProtocol` 方法清单、`interrupt_on` 行为、updates 流节点结构（供 Task 2/3/5 引用）

- [ ] **Step 1: 更新 requirements.txt**

```python
# deepagents (编排核心)
deepagents==0.7.11
# 连带升级（deepagents 硬性要求）
langchain-core>=1.6.1
langchain>=1.3.18
langchain-anthropic>=1.7.0
```

运行 `pip install --dry-run -r requirements.txt` 本地不可用（无本地 venv），直接进入 Step 2 在服务器 dry-run。

- [ ] **Step 2: 服务器 dry-run 依赖解析**

```bash
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 \
  'cd /home/wangyan/deploy/eap/backend && .venv/bin/pip install --dry-run "deepagents==0.7.11" "langchain-core>=1.6.1" "langchain>=1.3.18" "langchain-anthropic>=1.7.0" 2>&1 | tail -5'
```

Expected: ResolutionImpossible 不出现；若冲突（langgraph 1.2.11 与 core 1.6.x），记录冲突对并在 Step 3 实际安装后跑冒烟决定锁定版本。

- [ ] **Step 3: 服务器安装（真实 venv + 符号链接）**

```bash
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 'cd /home/wangyan/eap/backend && .venv/bin/pip install -q "deepagents==0.7.11" "langchain-core>=1.6.1" "langchain>=1.3.18" "langchain-anthropic>=1.7.0"'
# 符号链接新包到 deploy venv（沿用既有模式）：
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 'python3 - <<PY
import os, glob
src = glob.glob("/home/wangyan/eap/backend/.venv/lib/python3.12/site-packages")[0]
dst = glob.glob("/home/wangyan/deploy/eap/backend/.venv/lib/python3.12/site-packages")[0]
for name in ["deepagents", "deepagents-0.7.11.dist-info", "langchain_core", "langchain_core-1.6", "langchain", "langchain-1.3", "langchain_anthropic", "langchain_anthropic-1.7", "langchain_classic", "langchain_classic-1.0", "langchain-community", "langchain_community"]:
    for p in glob.glob(os.path.join(src, name + "*")):
        target = os.path.join(dst, os.path.basename(p))
        if not os.path.lexists(target):
            os.symlink(p, target)
            print("symlink", os.path.basename(p))
PY'
```

Expected: 打印新包 symlink 列表；`sudo systemctl restart eap-backend` 后 health 正常（先重启旧代码，回归由 Task 3 承担——此步仅装包）。

- [ ] **Step 4: 写冒烟脚本**

`backend/scripts/spike_deepagents.py`（复制到服务器 /tmp 运行，不入最终代码）：

```python
"""Task 1 spike：锁定 deepagents 0.7.11 的关键接口形状"""
import asyncio, json, inspect
from dotenv import load_dotenv
load_dotenv("/home/wangyan/deploy/eap/backend/.env")

# 1. SandboxBackendProtocol 接口
from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol
print("=== BackendProtocol methods ===")
for name in ["ls", "read", "write", "edit", "glob", "grep"]:
    m = getattr(BackendProtocol, name, None)
    if m: print(name, inspect.signature(m))
print("=== SandboxBackendProtocol methods ===")
for name in ["execute"]:
    m = getattr(SandboxBackendProtocol, name, None)
    if m: print(name, inspect.signature(m))

# 2. create_deep_agent 签名
from deepagents import create_deep_agent
print("=== create_deep_agent ===")
print(inspect.signature(create_deep_agent))

# 3. 最小图流式冒烟（DeepSeek 模型 + 双流模式）
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg_pool
import os

pool = psycopg_pool.ConnectionPool(
    "postgresql://eap:eap_dev_2024@127.0.0.1:5432/eap".replace("eap_dev_2024", os.getenv("EAP_DB_PW", "")),
    min_size=1, max_size=2, open=True, timeout=10)
checkpointer = PostgresSaver(pool)

llm = ChatOpenAI(model="deepseek-v4-pro", api_key=os.getenv("DEEPSEEK_API_KEY"),
                 base_url="https://api.deepseek.com/v1", max_tokens=256, stream_usage=True)
graph = create_deep_agent(model=llm, tools=[], checkpointer=checkpointer)

async def main():
    config = {"configurable": {"thread_id": "spike:1:test"}}
    async for item in graph.astream({"messages": [("user", "列出你的可用工具，不要调用")]},
                                    config, stream_mode=["messages", "updates"]):
        mode, payload = item
        if mode == "messages":
            chunk, meta = payload
            if getattr(chunk, "content", None):
                print("MSG chunk:", repr(chunk.content)[:40])
        else:
            for node, out in payload.items():
                print("UPDATE node:", node, "| keys:", list(out.keys())[:6],
                      "| msgs:", [type(m).__name__ for m in out.get("messages", [])][:6])

asyncio.run(main())
```

- [ ] **Step 5: 服务器运行冒烟**

```bash
scp backend/scripts/spike_deepagents.py wangyan@192.168.1.51:/tmp/
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 \
  'cd /home/wangyan/deploy/eap/backend && EAP_DB_PW=eap_dev_2024 PYTHONPATH=. .venv/bin/python /tmp/spike_deepagents.py 2>&1 | grep -v DeprecationWarning | head -40'
```

Expected: 打印协议方法签名 + create_deep_agent 签名 + MSG chunk 逐 token + UPDATE 节点结构与消息类型。**将输出抄录到本计划文档附录**（Task 3/5 的映射代码以实测形状为准；若 updates 含 `write`/`execute`/`task` 等子节点名，映射层按节点名路由 tool 事件）。

- [ ] **Step 6: 提交**

```bash
git add backend/requirements.txt backend/scripts/spike_deepagents.py
git commit -m "chore: 引入 deepagents 0.7.11 及依赖升级 + 冒烟脚本"
```

---

### Task 2: 执行后端实现（filesystem + docker）

**Files:**
- Create: `backend/app/core/agent/backends/__init__.py`
- Create: `backend/app/core/agent/backends/filesystem_backend.py`
- Create: `backend/app/core/agent/backends/docker_backend.py`
- Test: 服务器 python 直调（无 pytest）

**Interfaces:**
- Consumes: Task 1 冒烟锁定的 `BackendProtocol`/`SandboxBackendProtocol` 方法签名
- Produces:
  - `build_workspace_root(tenant_id: str, user_id: str, thread_id: str) -> str`
  - `build_backend(mode: str, tenant_id: str, user_id: str, thread_id: str) -> BackendProtocol`（mode ∉ {local, container} 或 Docker 不可用时 raise `BackendUnavailableError(message)`）
  - `class BackendUnavailableError(Exception)`

- [ ] **Step 1: 写 backend 工厂与异常**

`backend/app/core/agent/backends/__init__.py`：

```python
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
```

- [ ] **Step 2: 写 filesystem backend**

`backend/app/core/agent/backends/filesystem_backend.py`：

```python
"""local 后端 — deepagents FilesystemBackend + 线程隔离目录"""
import os
from deepagents.backends.filesystem import FilesystemBackend


def build_filesystem_backend(root: str) -> FilesystemBackend:
    os.makedirs(root, exist_ok=True)
    return FilesystemBackend(root_dir=root)
```

- [ ] **Step 3: 写 docker backend（方法签名以 Task 1 冒烟实测为准，此处为 0.7.x 预期形状）**

`backend/app/core/agent/backends/docker_backend.py`：

```python
"""container 后端 — 一次性 Docker 容器沙箱（SandboxBackendProtocol）

沙箱参数：--network none --memory 256m --cpus 1 --pids-limit 64
文件持久化：宿主 root_dir 挂载到容器 /workspace
镜像：python:3.12-slim（部署时预热）
"""
import subprocess
from pathlib import Path
from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol

IMAGE = "python:3.12-slim"
EXEC_TIMEOUT = 10


def _run_container(root_dir: str, code: str) -> str:
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", "256m", "--cpus", "1", "--pids-limit", "64",
        "-v", f"{root_dir}:/workspace",
        "-w", "/workspace",
        IMAGE, "sh", "-c", code,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=EXEC_TIMEOUT)
    out = (r.stdout or "").strip()
    if r.stderr:
        out = (out + "\n" + r.stderr.strip()).strip()
    return out or "(无输出)"


class DockerBackend(SandboxBackendProtocol):
    def __init__(self, root_dir: str):
        # 构建时校验 Docker 可用 + 镜像存在（fail-closed 的第一道闸）
        chk = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                             capture_output=True, text=True, timeout=5)
        if chk.returncode != 0:
            raise RuntimeError(f"Docker 不可用: {chk.stderr.strip()}")
        img = subprocess.run(["docker", "image", "inspect", IMAGE],
                             capture_output=True, text=True, timeout=10)
        if img.returncode != 0:
            raise RuntimeError(f"镜像 {IMAGE} 缺失，请先 docker pull")
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    # ---- 文件操作：容器内执行，但文件都落在挂载的 /workspace ----
    def _fs(self, op: str) -> str:
        return _run_container(str(self.root_dir), f"{op}")

    def ls(self, path: str = ".") -> str:
        return self._fs(f"ls -la /workspace/{path}")

    def read(self, path: str) -> str:
        return self._fs(f"cat /workspace/{path}")

    def write(self, path: str, content: str) -> str:
        import json as _json
        quoted = _json.dumps(content)
        return self._fs(f"printf %s {quoted} > /workspace/{path} && echo 已写入 {path}")

    def edit(self, path: str, old: str, new: str) -> str:
        import json as _json
        o, n = _json.dumps(old), _json.dumps(new)
        return self._fs(f"sed -i s/{o}/{n}/g /workspace/{path} && echo 已编辑 {path}")

    def glob(self, pattern: str) -> str:
        return self._fs(f"find /workspace -name '{pattern}'")

    def grep(self, pattern: str, path: str = ".") -> str:
        return self._fs(f"grep -r '{pattern}' /workspace/{path}")

    # ---- shell（沙箱协议）：容器内执行任意命令 ----
    def execute(self, code: str) -> str:
        return _run_container(str(self.root_dir), code)
```

- [ ] **Step 4: 服务器验证（local + container + fail-closed）**

```bash
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 'python3 - <<PY
import sys; sys.path.insert(0, "/home/wangyan/deploy/eap/backend")
from dotenv import load_dotenv; load_dotenv("/home/wangyan/deploy/eap/backend/.env")
from app.core.agent.backends import build_backend, BackendUnavailableError

# local：写读闭环
fs = build_backend("local", "1", "1", "t1")
fs.write("hello.txt", "你好，EAP")
assert "你好" in fs.read("hello.txt"), "fs read 失败"
print("local backend OK")

# container：execute + 文件透传
dk = build_backend("container", "1", "1", "t2")
assert "1024" in dk.execute("python3 -c print(2**10)"), "container execute 失败"
assert "hello.txt" in dk.ls("."), "容器未看到宿主文件"
print("container backend OK")

# fail-closed
try:
    build_backend("k8s", "1", "1", "t3")
    raise SystemExit("应当抛异常")
except BackendUnavailableError as e:
    print("fail-closed OK:", e)
PY'
```

Expected: 三行 OK。若 docker 无执行权限，用 `echo $SSH_PASSWORD | sudo -S docker` 验证权限问题并修复（wangyan 加入 docker 组）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/agent/backends/
git commit -m "feat: 执行后端双实现（FilesystemBackend / DockerBackend fail-closed）"
```

---

### Task 3: DeepAgentFactory + orchestrator 瘦身（核心替换）

**Files:**
- Create: `backend/app/core/agent/deep_agent_factory.py`
- Modify: `backend/app/core/agent/orchestrator.py`（stream_chat 委托 factory；删除 `_get_or_build_graph`、`_build_skill_tools`、`_build_sub_agent_tools`；图缓存键扩展）
- Delete: `backend/app/core/agent/tools/code_execution.py`
- Modify: `backend/app/core/agent/tools/__init__.py`（DEFAULT_TOOLS 移除 code_execution）
- Test: 部署 + 全量回归 `bash scripts/eap_full_test.sh`（66 项必须全绿）

**Interfaces:**
- Consumes: Task 2 的 `build_backend`；Task 1 的 updates 形状记录
- Produces:
  - `TOOL_DISPLAY_NAMES: dict[str, str]`（deepagents 默认工具中文别名）
  - `class DeepAgentFactory`：`build(tenant_id, agent_id, user_id, provider_config, thread_id) -> tuple[graph, cache_key]`
  - orchestrator 对外签名不变：`stream_chat(user_message, thread_id, user_id, tenant_id, model_provider_id=None, agent_id=None)`

- [ ] **Step 1: 写工厂**

`backend/app/core/agent/deep_agent_factory.py`：

```python
"""DeepAgentFactory — 按 Agent 配置组装 deepagents 编译图

职责：读 AgentConfig / SubAgentDefinition / SkillConfig / ModelProvider，
组装 create_deep_agent 全部参数；按指纹缓存编译图。
"""
import hashlib
import logging

from deepagents import create_deep_agent

from app.models.agent_config import AgentConfig
from app.models.skill_config import SkillConfig
from app.models.sub_agent import SubAgentDefinition
from app.core.agent.backends import build_backend, build_workspace_root
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


class DeepAgentFactory:
    def __init__(self):
        self._cache: dict[str, object] = {}

    def build(self, tenant_id: str, agent_id: int | None, user_id: str,
              provider_config: dict, thread_id: str) -> tuple[object, str]:
        """组装 deepagent 编译图。返回 (graph, cache_key)。"""
        agent = None
        skills, subagents, interrupt_on, backend_mode, memory_root = [], [], [], "local", None
        tool_names = None

        if agent_id:
            agent = AgentConfig.query.filter_by(
                id=agent_id, tenant_id=int(tenant_id)).first()
        if agent:
            # tools_config：自有工具按配置过滤（code_execution 名字 → execute 开关）
            tool_names = set(agent.tools_config or [])
            backend_mode = (agent.backend or "local")
            interrupt_on = HITL_TOOLS if (agent.permission_mode or "default") == "default" else []

            # prompt 模式 skill → deepagents skills 目录（渐进披露）
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
        tools = self._filter_own_tools(tool_names)

        backend = build_backend(backend_mode, str(tenant_id), str(user_id), thread_id)
        memory_root = build_workspace_root(str(tenant_id), str(user_id), thread_id)

        cache_key = self._cache_key(tenant_id, agent_id, provider_config,
                                    tool_names, backend_mode, subagents)
        if cache_key in self._cache:
            return self._cache[cache_key], cache_key

        graph = create_deep_agent(
            model=provider_config["_llm"],
            tools=tools,
            subagents=subagents or None,
            skills=skills or None,
            backend=backend,
            memory=memory_root,   # 每线程目录内持久化用户记忆文件
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
            "name": f"sub_{sub.name}",
            "description": f"子代理「{sub.name}」: {(sub.role_prompt or '')[:100]}",
            "system_prompt": sub.role_prompt,
            "tools": sub.tools or [],
        }
        if sub.model_provider_id:
            from app.models.model_provider import ModelProvider
            mp = ModelProvider.query.filter_by(
                id=sub.model_provider_id, tenant_id=int(tenant_id)).first()
            if mp:
                spec["model"] = self._build_sub_llm(mp)
        return spec

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

    def _cache_key(self, tenant_id, agent_id, provider_config, tool_names,
                   backend_mode, subagents) -> str:
        endpoint = hashlib.sha256(
            f"{provider_config.get('api_base', '')}|{provider_config.get('api_key', '')}".encode()
        ).hexdigest()[:8]
        parts = [
            provider_config["provider"], provider_config["model_name"],
            ",".join(sorted(tool_names or [])) if tool_names is not None else "all",
            backend_mode,
            ",".join(sorted(s["name"] for s in subagents)),
            endpoint,
        ]
        return ":".join(parts)
```

- [ ] **Step 2: orchestrator 瘦身（stream_chat 改造 + 删三个旧方法）**

`orchestrator.py` 中 `stream_chat` 的 Step 1-2 区域替换为：

```python
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
        # ------------------------------------------------------------------
        from app.core.agent.deep_agent_factory import DeepAgentFactory
        factory = getattr(self, "_deep_factory", None) or DeepAgentFactory()
        self._deep_factory = factory
        graph, _cache_key = factory.build(
            tenant_id, agent_id, user_id, provider_config, thread_id)
```

同时删除方法：`_get_or_build_graph`、`_build_skill_tools`、`_build_sub_agent_tools`、`_build_mcp_tools` 的调用改为 factory 内不包含（MCP 工具并入 `_filter_own_tools` 前的 `self._resolve_tools`——**保留 `_resolve_tools` 与 MCP 客户端缓存逻辑**，改为返回工具列表后交给 factory：将 `_resolve_tools` 的返回并入 factory.build 的 tools 参数）。

> 实现注意：`_resolve_tools` 内部已含 skill/sub-agent 工具构建 —— 本次改造中它只保留 DEFAULT_TOOLS 过滤 + MCP 工具（skill/sub-agent 逻辑随删除方法一并移除）。具体剪切点：`_resolve_tools` 中 `sub_tools = self._build_sub_agent_tools(...)` 与 `skill_tools = self._build_skill_tools(...)` 两行及后续合并删除，返回 `base_tools + mcp_tools`。

- [ ] **Step 3: tools/__init__.py 移除 code_execution + 删文件**

```python
from app.core.agent.tools.calculator import calculator_tool
from app.core.agent.tools.datetime_tool import datetime_tool
from app.core.agent.tools.web_search import web_search_tool
# code_execution 退役：deepagents 内置 execute 接管（沙箱协议），
# tools_config 中 "code_execution" 名字保留为 execute 启用开关
from app.core.agent.tools.knowledge_search import knowledge_search_tool
from app.core.agent.tools.memory_tools import memory_save_tool, memory_search_tool
from app.core.agent.tools.skill_file_tool import read_skill_file_tool

DEFAULT_TOOLS = [
    calculator_tool,
    datetime_tool,
    web_search_tool,
    knowledge_search_tool,
    memory_save_tool,
    memory_search_tool,
    read_skill_file_tool,
]
```

`rm backend/app/core/agent/tools/code_execution.py`

- [ ] **Step 4: 部署 + 全量回归**

```bash
python3 -m py_compile backend/app/core/agent/orchestrator.py backend/app/core/agent/deep_agent_factory.py backend/app/core/agent/backends/*.py
make deploy
bash scripts/eap_full_test.sh
```

Expected: 66 项全绿（此步可能暴露 updates 流映射问题 —— 若 SSE 事件缺失/重复，在 orchestrator 事件循环中按 Task 1 实测的节点结构适配 tool_end 路由，直至回归全绿）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/
git commit -m "feat: deepagents 编排核心替换（DeepAgentFactory + orchestrator 瘦身）"
```

---

### Task 4: 子 agent 模型绑定 + 资源列表扩展

**Files:**
- Modify: `backend/app/models/sub_agent.py`（加 model_provider_id）
- Modify: `backend/app/api/v1/orchestration.py`（create/update 接受字段）
- Modify: `backend/app/api/v1/agent.py`（`/agents/resources` 增加 deepagents 默认工具条目）
- Modify: `frontend/src/pages/AgentManager/index.tsx`（子 agent 表单加模型后端下拉）
- Modify: `frontend/src/types/orchestration.ts`（SubAgentInfo 加字段，若已分离类型）
- Test: 回归 + API 直测

**Interfaces:**
- Consumes: Task 3 的 `TOOL_DISPLAY_NAMES`
- Produces: 子 agent create/update 支持 `model_provider_id`；resources 列表含 deepagents 默认工具（id/name/description/display_name）

- [ ] **Step 1: 模型层 + 服务器加列**

```python
# sub_agent.py 在 tools 字段后加：
model_provider_id = db.Column(
    db.Integer, db.ForeignKey("model_providers.id")
)  # 子代理独立模型后端，为空时继承主代理
```

服务器执行（复用 dotenv 加载模式）：

```bash
sshpass -p "$SSH_PASSWORD" ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 \
  "cd /home/wangyan/deploy/eap/backend && .venv/bin/python -c \"
from dotenv import load_dotenv; load_dotenv('/home/wangyan/deploy/eap/backend/.env')
from app import create_app
from app.extensions import db
from sqlalchemy import text
app = create_app('production')
with app.app_context():
    db.session.execute(text('ALTER TABLE sub_agent_definitions ADD COLUMN IF NOT EXISTS model_provider_id INTEGER REFERENCES model_providers(id)'))
    db.session.commit()
    print('列已就绪')\""
```

- [ ] **Step 2: API 接受字段**

`orchestration.py` 的 `create_sub_agent`：

```python
    sub = SubAgentDefinition(
        tenant_id=g.tenant_id, parent_agent_id=agent_id,
        name=data["name"], role_prompt=data["role_prompt"],
        tools=data.get("tools", []), model=data.get("model"),
        model_provider_id=data.get("model_provider_id"),
        mode=data.get("mode", "inline"),
    )
```

- [ ] **Step 3: resources 列表加默认工具**

`agent.py` 的 `/agents/resources` 返回中追加：

```python
    # deepagents 默认工具（统一开关：默认全开）
    from app.core.agent.deep_agent_factory import TOOL_DISPLAY_NAMES
    DEEP_DEFAULT_TOOLS = [
        ("write_todos", "任务规划清单"), ("ls", "列出文件"),
        ("read_file", "读取文件"), ("write_file", "写入文件"),
        ("edit_file", "编辑文件"), ("glob", "按模式查找文件"),
        ("grep", "内容搜索"), ("task", "子代理调度"),
    ]
    for tid, tdesc in DEEP_DEFAULT_TOOLS:
        result["tools"].append({
            "id": tid, "name": tid, "description": tdesc,
            "display_name": TOOL_DISPLAY_NAMES.get(tid, tid),
        })
```

- [ ] **Step 4: 前端子 agent 表单**

`AgentManager/index.tsx` 子 agent Modal 表单（与主 agent 相同模式）：

```tsx
<Form.Item name="model_provider_id" label="模型后端"
  tooltip="子代理使用的模型供应商；不选则继承主代理">
  <Select style={{ width: 220 }} allowClear placeholder="继承主代理"
    options={availableModels.map((m) => ({
      label: `${m.name}${m.is_default ? ' (默认)' : ''}`, value: m.id }))} />
</Form.Item>
```

- [ ] **Step 5: 部署 + 回归 + 直测**

```bash
make deploy
bash scripts/eap_full_test.sh
# 直测：子代理绑定模型后端往返
```

Expected: 回归全绿 + 子代理 to_dict 含 model_provider_id。

- [ ] **Step 6: 提交**

```bash
git add backend/ frontend/
git commit -m "feat: 子代理模型绑定 + deepagents 默认工具资源列表"
```

---

### Task 5: HITL 接通（interrupt 审批流转）

**Files:**
- Modify: `backend/app/api/v1/chat.py`（resume 模式 + interrupt 事件透传）
- Modify: `backend/app/api/v1/workflow.py`（approve/reject/edit_and_approve 落库后由 orchestrator 恢复时读取）
- Modify: `backend/app/core/agent/orchestrator.py`（interrupt 检测 → 建 ApprovalRequest → 发 interrupt 事件；resume 路径读取审批决定 → Command(resume=...)）
- Modify: `backend/app/models/approval.py`（无需改表：字段已齐全）
- Test: HITL 用例直测 + 回归

**Interfaces:**
- Consumes: Task 3 的 factory（interrupt_on 已传入）
- Produces: SSE `interrupt` 事件 `{"type": "interrupt", "approval_id": N, "tool_name": str, "args": dict}`；`/chat/stream` 接受 `"resume": true`（message 为空）；恢复值协议：approve → `Command(resume={"action": "approve"})`，reject → `Command(resume={"action": "reject"})`，edited → `Command(resume={"action": "edited", "args": {...}})`

- [ ] **Step 1: chat.py resume 模式**

```python
    data = request.get_json()
    if not data or ("message" not in data and not data.get("resume")):
        return Response(
            f"data: {json.dumps({'type': 'error', 'message': 'message is required'})}\n\n",
            mimetype="text/event-stream",
        ), 422

    user_message = data.get("message", "")
    resume = bool(data.get("resume"))
    ...
    # 围栏只对非空新消息执行
    if user_message and not resume:
        (现有围栏检查块保持)
```

- [ ] **Step 2: orchestrator interrupt 检测与审批落库**

`stream_chat` 的 graph.stream 循环外层，用 `graph.get_state(config)` 在流结束后检测 `__interrupt__`：

```python
        # 流结束后检测 HITL 中断
        from app.models.approval import ApprovalRequest
        state = graph.get_state(config)
        interrupts = (state.interrupts or []) if state else []
        for intr in interrupts:
            payload = intr.value if isinstance(intr.value, dict) else {}
            tool_name = payload.get("tool_name") or payload.get("tool") or "unknown"
            tool_args = payload.get("args") or payload.get("tool_args") or {}
            appr = ApprovalRequest(
                tenant_id=int(tenant_id), thread_id=thread_id,
                agent_name=None, tool_name=tool_name, tool_args=tool_args,
                status="pending", requested_by=int(user_id),
            )
            db.session.add(appr)
            db.session.commit()
            yield f"data: {json.dumps({'type': 'interrupt', 'approval_id': appr.id, 'tool_name': tool_name, 'args': tool_args}, ensure_ascii=False)}\n\n"
```

- [ ] **Step 3: resume 路径**

`stream_chat` 增加 resume 分支（在组装图之前）：

```python
        if resume:
            # 读取该 thread 最近的 pending 审批，按其决定构建恢复值
            from app.models.approval import ApprovalRequest
            from langgraph.types import Command
            pending = ApprovalRequest.query.filter_by(
                tenant_id=int(tenant_id), thread_id=thread_id, status="pending"
            ).order_by(ApprovalRequest.created_at.desc()).first()
            if not pending:
                yield f"data: {json.dumps({'type': 'error', 'message': '没有待恢复的审批'}, ensure_ascii=False)}\n\n"
                return
            if pending.decision == "reject":
                resume_cmd = Command(resume={"action": "reject"})
            elif pending.decision == "approve" and pending.edited_args:
                resume_cmd = Command(resume={"action": "edited", "args": pending.edited_args})
            else:
                resume_cmd = Command(resume={"action": "approve"})
            pending.status = "resumed" if pending.status == "pending" else pending.status
            # 审批状态已由 workflow API 置为 approved/rejected（decision 字段），
            # 这里标记已消费，防止重复恢复
            db.session.commit()
            graph = (已构建的 graph)
            for stream_item in graph.stream(resume_cmd, config, stream_mode=["messages", "updates"]):
                (与正常流相同的 SSE 映射循环 —— 提取为内部生成器 _map_stream(graph.stream(...)))
```

> 实现注意：将现有双流映射循环提取为 `_emit_stream(stream_iter)` 内部生成器，正常与 resume 两条路径共用。

- [ ] **Step 4: workflow.py 保持不变（验证已有 API 语义匹配）**

approve/reject/edit_and_approve 已写入 `status`/`decision`/`edited_args` —— 确认 `reject` 端点写 `decision="reject"`、`edit_and_approve` 写 `decision="approve"` + `edited_args`，与 Step 3 读取字段一致；不一致处微调。

- [ ] **Step 5: HITL 直测（服务器）**

```bash
# 1. default 模式 agent 请求写文件 → interrupt 事件
# 2. 审批列表出现 pending 记录
# 3. approve → resume → 工具执行 + 流式继续
# 4. 再测 reject → 工具跳过且模型收到说明
```

按现有 SSE 测试方式逐步断言（事件序列：... → interrupt → (审批) → resume 后 token/done）。

- [ ] **Step 6: 全量回归 + 提交**

```bash
bash scripts/eap_full_test.sh
git add backend/
git commit -m "feat: HITL 人机协同接通（interrupt 审批流转 + resume）"
```

---

### Task 6: 前端 HITL 审批卡 + 工具展示升级

**Files:**
- Modify: `frontend/src/types/chat.ts`（SSEEvent 加 interrupt；ChatMessage 加 displayName）
- Modify: `frontend/src/api/chat.ts`（interrupt 回调 + resume 请求支持）
- Modify: `frontend/src/stores/chatStore.ts`（interrupt 事件 → 待审批消息；resumeChat action）
- Modify: `frontend/src/pages/Chat/index.tsx`（审批卡组件 + 自动 resume）
- Modify: `frontend/src/pages/AgentManager/index.tsx`（子代理模型下拉已在 Task 4；工具勾选 display_name）
- Test: build + 部署 + SSE 全链路冒烟

**Interfaces:**
- Consumes: Task 5 的 interrupt 事件协议
- Produces: 前端审批卡：批准 → POST `/workflow/approvals/{id}/approve` → 自动 `sendMessage('', threadId, …, {resume: true})`

- [ ] **Step 1: 类型与 API 层**

`types/chat.ts`：

```ts
export interface SSEEvent {
  type: 'token' | 'tool_start' | 'tool_end' | 'error' | 'done' | 'thread_id' | 'guardrail' | 'interrupt';
  approval_id?: number;
  tool_name?: string;
  args?: Record<string, unknown>;
  display_name?: string;
}
```

`api/chat.ts` 增加：

```ts
    onInterrupt: (approvalId: number, toolName: string, args: Record<string, unknown>) => void;
    // streamChat 增加 resume 参数：resume 时 message 传空串 + resume: true
```

- [ ] **Step 2: store 增加待审批状态**

```ts
// chatStore 状态追加：
pendingApproval: { approvalId: number; toolName: string; args: string; threadId: string } | null,
// onInterrupt 回调：写入 pendingApproval（threadId 用 _tid()）
// resumeChat(approvalId, decision, editedArgs?)：
//   先 await apiClient.post(`/workflow/approvals/${approvalId}/${decision==='reject'?'reject':'approve'}`, ...)
//   再 streamChat('', tid, ..., {resume:true}) 复用现有 onToken/onTool 回调链
```

- [ ] **Step 3: Chat 页审批卡**

`Chat/index.tsx` 在输入区上方渲染（pendingApproval 非空时）：

```tsx
{pendingApproval && (
  <div style={{ border: '1px solid #fde68a', background: '#fef3c7', borderRadius: 10, padding: '10px 14px', marginBottom: 10, fontFamily: T.mono, fontSize: 12 }}>
    <div style={{ fontWeight: 700, marginBottom: 4 }}>⏸ 待人工审批 · {pendingApproval.toolName}</div>
    <div style={{ color: T.ink2, marginBottom: 8, whiteSpace: 'pre-wrap', maxHeight: 120, overflowY: 'auto' }}>{pendingApproval.args}</div>
    <Space>
      <Button size="small" type="primary" onClick={() => resumeChat(pendingApproval.approvalId, 'approve')}>批准执行</Button>
      <Button size="small" danger onClick={() => resumeChat(pendingApproval.approvalId, 'reject')}>拒绝</Button>
    </Space>
  </div>
)}
```

- [ ] **Step 4: 工具名展示升级**

`MessageBubble` 的 ToolRow：`msg.toolName` 优先用 `msg.displayName || msg.toolName`（store 的 onToolStart 记录 `event.display_name`）。

- [ ] **Step 5: 构建 + 部署 + 冒烟**

```bash
cd frontend && npm run build
make deploy
# SSE 冒烟：default 模式 agent 触发写文件 → 观察 interrupt 事件 → 审批卡逻辑由回归用例验证
bash scripts/eap_full_test.sh
```

- [ ] **Step 6: 提交**

```bash
git add frontend/
git commit -m "feat: 前端 HITL 审批卡 + resume + 工具中文别名"
```

---

### Task 7: 收尾（文档 + 回归 + 合并）

**Files:**
- Modify: `CLAUDE.md`（架构段更新：deepagents 编排核心）
- Modify: `.claude/skills/deploy-eap/SKILL.md`（补充 deepagents 依赖与 workspace 目录）
- Test: 最终全量回归

- [ ] **Step 1: 文档更新**

CLAUDE.md 的 Agent 段更新为：

```markdown
**Agent**: `app/core/agent/deep_agent_factory.py` — 基于 deepagents 的编排核心：
create_deep_agent 组装（skills 渐进披露 / subagents / memory / backend 沙箱），
后端双实现（FilesystemBackend local / DockerBackend container），
HITL 通过 interrupt_on + ApprovalRequest 审批流转。模型选择动态解析
（聊天页 > 智能体绑定 > 租户默认），图按指纹缓存。
```

- [ ] **Step 2: 最终回归 + 冒烟（含容器模式 agent 对话）**

```bash
bash scripts/eap_full_test.sh
# 容器模式冒烟：backend=container 的 agent 执行 print(2**10) → 1024
```

- [ ] **Step 3: 提交 + 合并说明**

```bash
git add CLAUDE.md .claude/skills/deploy-eap/SKILL.md
git commit -m "docs: 架构文档同步 deepagents 化"
```

完成后向用户报告分支状态与合并建议（merge 到 main 由用户确认后执行）。

---

## Self-Review 记录

1. **Spec coverage**：规格 §3 架构 → Task 3；§4 映射 → Task 3/4；§4.1 默认工具 → Task 3/4；§5 后端 → Task 2；§6 SSE → Task 1/3/5；§7 错误处理 → Task 2（fail-closed）；§7.1 HITL → Task 5/6；§8 文件结构 → Task 2/3/4；§9 依赖 → Task 1；§10 测试 → 各任务回归步骤 + Task 7。无遗漏。
2. **Placeholder scan**：Task 3 Step 2 含"实现注意"剪切点说明（非占位，是明确的删除/保留指引）。Task 1 冒烟输出附录由实施者抄录 —— 该不确定性是规格 §6 声明的"技术验证点"，已在计划中显式闭环（抄录后据此适配）。
3. **Type consistency**：`build_backend(mode, tenant_id, user_id, thread_id)` 在 Task 2 定义、Task 3 调用一致；`TOOL_DISPLAY_NAMES` 在 Task 3 定义、Task 4 引用一致；interrupt 事件字段 `approval_id/tool_name/args` 在 Task 5 产出、Task 6 消费一致；`DeepAgentFactory.build` 签名在 Task 3 定义且 orchestrator 调用一致。
