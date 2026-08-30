"""Task 2 补充冒烟：继承自 BaseSandbox 的 edit/read/grep 容器内 python 脚本路径、
失败命令退出码透传、越界路径 fail-closed 拒绝。"""
import sys

sys.path.insert(0, "/home/wangyan/deploy/eap/backend")
from dotenv import load_dotenv

load_dotenv("/home/wangyan/deploy/eap/backend/.env")

from app.core.agent.backends import build_backend

dk = build_backend("container", "1", "1", "t1")

# edit + read（BaseSandbox._edit_inline 容器内 python 脚本）
w = dk.write("/workspace/editme.txt", "aaa bbb aaa")
assert w.error is None, w
ed = dk.edit("/workspace/editme.txt", "bbb", "CCC")
assert ed.error is None and ed.occurrences == 1, ed
r = dk.read("/workspace/editme.txt")
assert r.error is None and "CCC" in r.file_data["content"], r
print("container edit+read OK")

# 失败命令：非零退出码透传
e = dk.execute("exit 7")
assert e.exit_code == 7 and "Exit code: 7" in e.output, e
print("exit-code passthrough OK")

# 越界路径拒绝（防宿主机逃逸，fail-closed）
u = dk.write("/etc/eap_escape_test", "x")
assert u.error is not None and "invalid_path" in u.error, u
print("escape blocked OK")

# grep 经容器内 python 脚本（edit 后内容为 "aaa CCC aaa"）
g = dk.grep("aaa", path="/workspace")
assert any("aaa" in m["text"] and m["path"] == "/workspace/editme.txt" for m in (g.matches or [])), g
print("container grep OK")

print("ALL EXTRA OK")
