---
name: deploy-eap
description: EAP 项目部署操作手册 — make deploy 系列命令、SSH 服务器信息、部署陷阱（.env 被 rsync --delete 删除、双 venv）、部署后强制验证清单
---

# EAP 部署操作

## 服务器信息

- SSH: `wangyan@192.168.1.51`（密码在本地 .make.env 的 SSH_PASSWORD，不提交仓库）
- 部署目录: `/home/wangyan/deploy/eap`
- 后端: systemd `eap-backend`（Gunicorn :5003），日志 `/home/wangyan/deploy/eap/logs/error.log`
- Nginx: `/etc/nginx/sites-enabled/eap`（`/eap/` 前缀路由）

## 部署命令（Makefile）

| 命令 | 作用 |
|---|---|
| `make deploy` | 完整部署：前端构建 + 后端同步 + pip install + 重启 + health 检查 |
| `make deploy-backend` | 仅同步后端 + 重启（**不含 pip install**） |
| `make deploy-frontend` | 仅构建并同步前端 |
| `make deploy-nginx` | 更新 Nginx 配置（`scripts/nginx_eap.conf`） |
| `make deploy-restart` | 仅重启后端 |
| `make server-info` | 服务状态 / 端口 / 磁盘 |

## ⚠️ 部署陷阱

### 1. rsync --delete 会删除服务器上的 .env

backend 同步带 `--delete`，本地仓库没有 `.env` 文件 → 服务器 `/home/wangyan/deploy/eap/backend/.env`（含 `DEEPSEEK_API_KEY`）会被删除，导致 401 "Authentication Fails"。

- Makefile 已加 `--exclude='.env'`，但**全新服务器首次部署**仍需手动创建 .env
- 每次部署后立即验证：`ssh wangyan@192.168.1.51 'wc -c /home/wangyan/deploy/eap/backend/.env'`（非 0 即存活）
- .env 内容：`DEEPSEEK_API_KEY=<完整 35 位 key>`。key 丢失时从 PG 取回：
  `SELECT api_key FROM model_providers WHERE name LIKE '%deepseek%';`

### 2. 双 venv 陷阱

- 真实包安装位置：`/home/wangyan/eap/backend/.venv`
- gunicorn 运行用：`/home/wangyan/deploy/eap/backend/.venv`（site-packages 通过符号链接指向前者）
- 新增 Python 依赖：更新 requirements.txt 后用 `make deploy`（含 pip install）。若服务器上 import 新包失败，检查上述 symlink 是否失效并重建。

### 3. SSH 偶发超时/拒绝

随机发生，重试即可（非配置问题）。

### 4. sudo 凭证缓存过期导致重启失败（已修复）

Makefile 已统一改为 `echo $SSH_PASSWORD | sudo -S` 管道传密码（不再依赖 sudo 凭证缓存）。`deploy-nginx` 因 sudo -S 与 stdin 传配置冲突，改为 scp 到 /tmp 再 sudo 复制。

手动操作服务器时仍可用等价写法（sudo 密码与 SSH 密码相同）：

```bash
SSHPASS="$SSH_PASSWORD" sshpass -e ssh -o StrictHostKeyChecking=no wangyan@192.168.1.51 \
  'echo $SSH_PASSWORD | sudo -S systemctl restart eap-backend && sleep 3 && curl -s http://127.0.0.1:5003/health'
```

### 5. requirements.txt 版本约束必须对齐服务器 1.x 栈

服务器实际运行 LangChain/LangGraph **1.x**（langchain-core 1.5.x）。requirements.txt 若回退到 0.3.x 约束会与 `langsmith==0.3.*` 冲突（pip ResolutionImpossible）。改动依赖版本前先在服务器 dry-run：
`cd /home/wangyan/deploy/eap/backend && .venv/bin/pip install --dry-run -r requirements.txt`

deepagents 版本约束（当前 `deepagents==0.7.11`）：硬性要求 `langsmith>=0.11.2`，`deepagents` / `langsmith` 两个 pin 必须同向升级，否则 pip 解析冲突（见 requirements.txt 内注释）。

### 6. Agent 工作区与容器沙箱（deepagents 后端）

- **工作区目录**：`/home/wangyan/deploy/eap/agent_workspaces`（`app/core/agent/backends/__init__.py` 的 `WORKSPACE_BASE`）。每线程独立目录 `{tenant}/{user}/{thread}` 三级隔离，随对话产生；rsync `--delete` 不受影响（该目录在 deploy 目录内但非 backend/ 子路径）。
- **container 后端**：一次性 `python:3.12-slim` 容器沙箱（`--network none --memory 256m --cpus 1 --pids-limit 64`），宿主线程工作目录挂载为容器内 `/workspace`，平台记忆落 `root_dir/memory/`。
- **镜像缺失 = fail-closed**：`build_backend("container", ...)` 构建失败抛 `BackendUnavailableError`，对话直接 error 事件（绝不回退宿主机执行）。排查：`docker images python:3.12-slim` → 缺失则 `docker pull python:3.12-slim`，然后重启 `eap-backend`。
- **容器冒烟**：`python3 -c "print(2**10)"` 经 execute 应返回 `1024`（backend=container 的 agent 对话验证，见 `backend/scripts/verify_backends.py`）。

## 部署 SOP（每次代码修改后必须执行）

1. 代码修改完成
2. 部署：后端改动 → `make deploy`；仅前端 → `make deploy-frontend`
3. 验证 .env 存活（陷阱 1）
4. 健康检查：`curl -s http://192.168.1.51:5003/health` → `{"status":"ok"}`
5. 回归测试：`bash scripts/eap_full_test.sh`（全功能测试套件：认证/RBAC/CRUD/Agent 工具调用/监控 trace/清理，退出码 0 即通过；日常快速验证可只跑浏览器聊天，确认 SSE 流式输出正常、工具调用正常）
6. 失败排查：
   - `sudo systemctl status eap-backend`
   - `tail -f /home/wangyan/deploy/eap/logs/error.log`（应用异常在 `logs/stderr.log`）

## 回滚

服务器无 git。回滚 = 本地恢复旧代码 → 重新部署（`make deploy-backend` / `make deploy-frontend`）。

## 部署验证时常见故障速查

| 错误 | 原因 |
|---|---|
| 401 "Authentication Fails" | .env 被删或 key 截断（陷阱 1） |
| "couldn't get a connection" | PG 连接串 / psycopg_pool 配置问题 |
| "insufficient tool messages" | 慢速工具调用导致 checkpoint 不完整（orchestrator 已有自动清理） |
