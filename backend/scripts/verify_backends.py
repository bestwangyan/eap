"""Task 2 验证脚本（无 pytest）：local 写读闭环 / container execute+透传 / fail-closed。

与 brief Step 4 的两处必要适配（详见 task-2-report §2 偏差）：
1. 结果类型按实测协议为结构化 dataclass（LsResult/ReadResult/WriteResult/ExecuteResponse），
   断言改为字段级检查。
2. brief 中 fs 用 t1、dk 用 t2 —— 两线程工作目录不同，文件透传断言必然失败；
   改为同线程 t1 共享 root_dir，分别验证 host→container 与 container→host 两个方向。
"""
import sys

sys.path.insert(0, "/home/wangyan/deploy/eap/backend")
from dotenv import load_dotenv

load_dotenv("/home/wangyan/deploy/eap/backend/.env")

from app.core.agent.backends import BackendUnavailableError, build_backend

# ---- local：写读闭环（结构化结果）----
fs = build_backend("local", "1", "1", "t1")
fs.write("hello.txt", "你好，EAP")
r = fs.read("hello.txt")
assert r.error is None and "你好" in r.file_data["content"], f"fs read 失败: {r}"
print("local backend OK")

# ---- container：execute 2**10 ----
# 注：brief 原文 `python3 -c print(2**10)` 缺引号，sh 解析括号报错；补引号。
dk = build_backend("container", "1", "1", "t1")  # 与 fs 同线程，共享 root_dir
e = dk.execute('python3 -c "print(2**10)"')
assert e.exit_code == 0 and "1024" in e.output, f"container execute 失败: {e}"
print("container execute OK:", e.output.strip())

# ---- 文件透传 host → container（挂载视角）----
ls = dk.ls(".")
paths = [x["path"] for x in (ls.entries or [])]
assert any(p.endswith("hello.txt") for p in paths), f"容器未看到宿主文件: {paths}"
print("host->container passthrough OK:", paths)

# ---- 文件透传 container → host（容器写入落盘到宿主）----
w = dk.write("/workspace/from_container.txt", "容器写入")
assert w.error is None, f"容器写文件失败: {w}"
r2 = fs.read("from_container.txt")
assert r2.error is None and "容器写入" in r2.file_data["content"], f"宿主未看到容器文件: {r2}"
print("container->host passthrough OK")

# ---- fail-closed：未知 mode 必须抛 BackendUnavailableError ----
try:
    build_backend("k8s", "1", "1", "t3")
    raise SystemExit("应当抛异常")
except BackendUnavailableError as ex:
    print("fail-closed OK:", ex)

print("ALL OK")
