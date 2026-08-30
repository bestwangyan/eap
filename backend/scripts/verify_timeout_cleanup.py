"""Task 2 修复验证：超时路径容器清理（--cidfile + docker rm -f）。

覆盖 review 指出的泄漏路径（此前从未被测试过）：
1. execute("sleep 100", timeout=3) -> 超时错误，且无残留容器（docker ps -a 计数前后一致）
2. 正常路径不受破坏：execute('python3 -c "print(2**10)"') -> 0 / 1024
3. cidfile 正常退出与超时后均无残留

运行（服务器侧，需在部署目录内以 venv python 执行）：
  cd /home/wangyan/deploy/eap/backend && .venv/bin/python /tmp/verify_timeout_cleanup.py
"""
import subprocess
import sys

sys.path.insert(0, "/home/wangyan/deploy/eap/backend")
from dotenv import load_dotenv

load_dotenv("/home/wangyan/deploy/eap/backend/.env")

from app.core.agent.backends import build_backend

IMAGE = "python:3.12-slim"


def count_containers() -> int:
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"ancestor={IMAGE}", "--format", "{{.ID}}"],
        capture_output=True, text=True, timeout=30,
    )
    return len([x for x in r.stdout.splitlines() if x.strip()])


def leftover_cidfiles(root: str) -> int:
    r = subprocess.run(
        ["bash", "-c", f"ls {root}/.eap-cid-* 2>/dev/null | wc -l"],
        capture_output=True, text=True, timeout=10,
    )
    return int(r.stdout.strip() or "0")


before = count_containers()
print(f"containers before: {before}")

dk = build_backend("container", "1", "1", "t1")
root = dk.root_dir

# ---- 1) 超时路径：sleep 100, timeout=3 ----
e = dk.execute("sleep 100", timeout=3)
print(f"timeout result: exit_code={e.exit_code}")
print(f"timeout output: {e.output!r}")
assert e.exit_code == 124, f"预期 124，实际 {e.exit_code}"
assert "timed out" in e.output.lower(), f"缺少超时文案: {e.output}"

after = count_containers()
print(f"containers after timeout: {after}")
assert after == before, f"超时后残留容器: before={before} after={after}（容器泄漏！）"
print("no leftover containers after timeout: OK")

left = leftover_cidfiles(root)
print(f"leftover cidfiles after timeout: {left}")
assert left == 0, f"超时后 cidfile 残留: {left}"

# ---- 2) 正常路径 ----
e2 = dk.execute('python3 -c "print(2**10)"')
print(f"normal result: exit_code={e2.exit_code} output={e2.output!r}")
assert e2.exit_code == 0 and "1024" in e2.output, f"正常路径被破坏: {e2}"

left2 = leftover_cidfiles(root)
print(f"leftover cidfiles after normal run: {left2}")
assert left2 == 0, f"正常退出后 cidfile 残留: {left2}"

final_count = count_containers()
assert final_count == before, f"最终容器计数不一致: before={before} after={final_count}"

print("ALL OK")
