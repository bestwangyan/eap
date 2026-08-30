"""Task-3 review 修复验证（Important 1/2/3 机制级冒烟，无 pytest）。

在服务器 venv 内运行（部署后）：
    cd /home/wangyan/deploy/eap/backend && .venv/bin/python scripts/verify_execute_switch.py

验证点：
I1. execute 开关（backend 变体控制，deepagents 0.7.11 无工具裁剪）：
  - build_backend("container", execute=False) 返回 DockerBackendNoShell，
    不实现 SandboxBackendProtocol（supports_execution == False）；
  - 真实调用路径模拟：FilesystemMiddleware._filter_unsupported_tools_and_apply_prompt
    —— 无 shell 后端下把 execute 从模型请求 tools 中剔除；
    完整 DockerBackend 对照 —— execute 保留；
  - factory 集成：临时 agent（container + tools_config 无 code_execution）→
    编译图 cache_key 含 noexec 段；含 code_execution → exec 段。
I2. code_execution-only agent 不回退全量：_resolve_tools 返回 []（
    review Important 2 修复，杜绝静默扩权）。
I3. 图缓存 LRU + evict：超限淘汰最久未用；evict(thread_id) 精确淘汰；
    iter_graphs() 公开遍历（review Important 3）。
"""
import sys
import uuid

sys.path.insert(0, "/home/wangyan/deploy/eap/backend")
from dotenv import load_dotenv

load_dotenv("/home/wangyan/deploy/eap/backend/.env")

from langchain.agents.middleware.types import ModelRequest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app import create_app
from app.core.agent.backends import build_backend
from app.core.agent.backends.docker_backend import DockerBackendNoShell
from app.core.agent.deep_agent_factory import CACHE_MAXSIZE as _CFG_MAX
from app.core.agent.orchestrator import AgentOrchestrator

FAKE_LLM = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}: {detail}")
        FAILED.append(name)


# ============ I1: backend 变体机制 ============
print("== I1 execute 开关（backend 变体）==")
from deepagents.backends.protocol import SandboxBackendProtocol
from deepagents.middleware.filesystem import FilesystemMiddleware, supports_execution

noshell = build_backend("container", "1", "1", "t_switch", execute=False)
shell = build_backend("container", "1", "1", "t_switch", execute=True)
check("I1a DockerBackendNoShell 类型", isinstance(noshell, DockerBackendNoShell))
check("I1b noshell 不实现 SandboxBackendProtocol",
      not isinstance(noshell, SandboxBackendProtocol))
check("I1c shell 实现 SandboxBackendProtocol",
      isinstance(shell, SandboxBackendProtocol))
check("I1d supports_execution(noshell)==False", supports_execution(noshell) is False)
check("I1e supports_execution(shell)==True", supports_execution(shell) is True)

# 真实调用路径：模型请求经 middleware 过滤后 execute 是否可见
mw_ns = FilesystemMiddleware(backend=noshell)
mw_sh = FilesystemMiddleware(backend=shell)
exec_tool_ns = next(t for t in mw_ns.tools if t.name == "execute")
exec_tool_sh = next(t for t in mw_sh.tools if t.name == "execute")

req_ns = ModelRequest(model=FAKE_LLM, messages=[HumanMessage("hi")], tools=[exec_tool_ns])
req_sh = ModelRequest(model=FAKE_LLM, messages=[HumanMessage("hi")], tools=[exec_tool_sh])
out_ns = mw_ns._filter_unsupported_tools_and_apply_prompt(req_ns)
out_sh = mw_sh._filter_unsupported_tools_and_apply_prompt(req_sh)
names_ns = [t.name for t in out_ns.tools]
names_sh = [t.name for t in out_sh.tools]
check("I1f noshell 请求 tools 无 execute", "execute" not in names_ns, names_ns)
check("I1g shell 请求 tools 保留 execute", "execute" in names_sh, names_sh)

# factory 集成：临时 agent 按 tools_config 选 backend 变体（rollback 不留库）
app = create_app()
with app.app_context():
    from app.extensions import db
    from app.models.agent_config import AgentConfig
    from app.core.agent.deep_agent_factory import DeepAgentFactory

    suffix = uuid.uuid4().hex[:8]
    a_noexec = AgentConfig(tenant_id=1, name=f"smoke_noexec_{suffix}",
                           backend="container", tools_config=["calculator"])
    a_exec = AgentConfig(tenant_id=1, name=f"smoke_exec_{suffix}",
                         backend="container",
                         tools_config=["calculator", "code_execution"])
    db.session.add_all([a_noexec, a_exec])
    db.session.flush()

    provider = {
        "provider": "test", "model_name": "smoke-model",
        "api_base": "http://127.0.0.1:9", "api_key": "sk-smoke",
        "_llm": FAKE_LLM, "_checkpointer": None,
    }
    factory = DeepAgentFactory()
    g1, k1 = factory.build("1", a_noexec.id, "1", provider, "t_switch", tools=None)
    g2, k2 = factory.build("1", a_exec.id, "1", provider, "t_switch", tools=None)
    check("I1h 无 code_execution → cache_key noexec 段", ":noexec:" in k1, k1)
    check("I1i 含 code_execution → cache_key exec 段", ":exec:" in k2, k2)

    # ============ I2: code_execution-only 不回退全量 ============
    print("== I2 code_execution-only 不静默扩权 ==")
    a_only = AgentConfig(tenant_id=1, name=f"smoke_only_{suffix}",
                         backend="container", tools_config=["code_execution"])
    db.session.add(a_only)
    db.session.flush()
    orch = AgentOrchestrator()
    resolved = orch._resolve_tools(a_only.id, "1")
    check("I2a code_execution-only → 空列表（不回退全量 7 工具）",
          resolved == [], f"got {len(resolved)} tools: {[t.name for t in resolved]}")
    check("I2b 无 tools_config 仍回退全量",
          len(orch._resolve_tools(None, "1")) == 7)
    a_calc = AgentConfig(tenant_id=1, name=f"smoke_calc_{suffix}",
                         backend="container", tools_config=["calculator"])
    db.session.add(a_calc)
    db.session.flush()
    resolved2 = orch._resolve_tools(a_calc.id, "1")
    check("I2c calculator-only → 仅 calculator",
          [t.name for t in resolved2] == ["calculator"], resolved2)

    # ============ I3: 图缓存 LRU + evict ============
    print("== I3 图缓存 LRU + evict ==")
    import app.core.agent.deep_agent_factory as daf
    daf.CACHE_MAXSIZE = 3
    f3 = DeepAgentFactory()
    keys = []
    for i in range(4):
        _, k = f3.build("1", a_calc.id, "1", provider, f"t_lru_{i}", tools=None)
        keys.append(k)
    check("I3a 超限后缓存封顶 3", len(f3._cache) == 3, len(f3._cache))
    check("I3b 最久未用（t_lru_0）被淘汰", keys[0] not in f3._cache,
          [k for k in f3._cache])
    check("I3c 最新（t_lru_3）保留", keys[3] in f3._cache)
    f3.evict("t_lru_1")
    check("I3d evict(thread_id) 精确淘汰", keys[1] not in f3._cache
          and keys[2] in f3._cache and keys[3] in f3._cache)
    check("I3e evict 后反向索引清空", "t_lru_1" not in f3._thread_keys)
    graphs = f3.iter_graphs()
    check("I3f iter_graphs() 公开遍历", len(graphs) == 2, len(graphs))
    daf.CACHE_MAXSIZE = _CFG_MAX
    f3.evict("t_lru_2")
    f3.evict("t_lru_3")
    check("I3g evict 后缓存清空", len(f3._cache) == 0, len(f3._cache))

    db.session.rollback()  # 临时 agent 不留库

# ============ I4: container 记忆路径映射（memory 中间件修复） ============
# 现场发现：MemoryMiddleware 对 /memory/AGENTS.md 调 download_files，
# 完整 DockerBackend 的 _map_to_host 曾只接受 /workspace 前缀 →
# invalid_path → ValueError → 聊天硬错误。修复后 /memory/* 显式映射
# root_dir/memory/*（本地/无 execute 变体 virtual_mode 同一落点）。
print("== I4 container 记忆路径映射 ==")
import tempfile as _tf
from pathlib import Path as _Path
from app.core.agent.backends.docker_backend import _map_to_host

with _tf.TemporaryDirectory() as tmp:
    root = _Path(tmp).resolve()
    check("I4a /workspace/x → root_dir/x",
          _map_to_host(root, "/workspace/foo/bar.txt") == root / "foo" / "bar.txt")
    check("I4b /memory/x → root_dir/memory/x",
          _map_to_host(root, "/memory/AGENTS.md") == root / "memory" / "AGENTS.md")
    check("I4c 越界路径 → None（fail-closed）",
          _map_to_host(root, "/etc/passwd") is None)
    check("I4d 穿越阻断 /memory/../etc → None",
          _map_to_host(root, "/memory/../etc/passwd") is None)
    check("I4e 穿越阻断 /workspace/../tmp → None",
          _map_to_host(root, "/workspace/../tmp/evil") is None)
    b = DockerBackendNoShell(root_dir=str(root))
    r = b.upload_files([("/memory/AGENTS.md", b"# memory")])
    ok = (r[0].error is None) and (root / "memory" / "AGENTS.md").read_text() == "# memory"
    check("I4f noshell upload /memory → root_dir/memory 落盘", ok)
    d = b.download_files(["/memory/AGENTS.md"])
    check("I4g noshell download /memory 往返一致", d[0].content == b"# memory")

print("=" * 40)
if FAILED:
    print(f"RESULT: FAIL ({len(FAILED)}): {FAILED}")
    sys.exit(1)
print("RESULT: ALL OK")
