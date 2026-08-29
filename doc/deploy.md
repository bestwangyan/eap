# EAP 企业 Agent 平台 — 部署文档

> **版本**: v1.1 | **日期**: 2026-07-25 | **服务器**: 192.168.1.51

---

## 目录

1. [服务器环境](#1-服务器环境)
2. [部署路径](#2-部署路径)
3. [依赖中间件](#3-依赖中间件)
4. [应用服务](#4-应用服务)
5. [Nginx 配置](#5-nginx-配置)
6. [环境变量](#6-环境变量)
7. [运维命令](#7-运维命令)
8. [访问方式](#8-访问方式)
9. [部署步骤](#9-部署步骤)

---

## 1. 服务器环境

| 项目 | 信息 |
|------|------|
| **服务器 IP** | `192.168.1.51` |
| **操作系统** | Ubuntu 24.04 |
| **SSH 用户** | `wangyan` |
| **Python** | 3.12.3 |
| **Node.js** | v22.23.1 |
| **可用内存** | ~5.2 GB |
| **可用磁盘** | ~59 GB |

---

## 2. 部署路径

```
/home/wangyan/deploy/eap/          # 项目根目录
├── backend/                        # 后端代码
│   ├── app/                        # Flask 应用
│   ├── .venv/                      # Python 虚拟环境
│   ├── .env                        # 环境变量（含 API Key）
│   ├── requirements.txt
│   └── wsgi.py
├── frontend/
│   └── dist/                       # 前端构建产物（静态文件）
├── logs/                           # 应用日志
│   ├── access.log
│   ├── error.log
│   ├── stdout.log
│   └── stderr.log
└── skills_storage/                 # Skill ZIP 解压存储
    └── {tenant_id}/
        └── {skill_name}/
```

### 2.1 配置文件位置

| 文件 | 路径 |
|------|------|
| Systemd 服务 | `/etc/systemd/system/eap-backend.service` |
| Nginx 站点 | `/etc/nginx/sites-enabled/eap` |
| 后端环境变量 | `/home/wangyan/deploy/eap/backend/.env` |

---

## 3. 依赖中间件

所有中间件为服务器原生安装（非容器化）。

### 3.1 PostgreSQL 16

| 参数 | 值 |
|------|-----|
| **地址** | `127.0.0.1:5432` |
| **数据库** | `eap` |
| **用户** | `eap` |
| **密码** | `CHANGE_ME` |
| **pg_hba** | `host all all 192.168.1.0/24 md5` |
| **扩展** | pgvector 0.6.0 |

```bash
# 连接命令
psql -h 127.0.0.1 -U eap -d eap
```

### 3.2 Redis 7

| 参数 | 值 |
|------|-----|
| **地址** | `127.0.0.1:6379` |
| **密码** | `CHANGE_ME` |
| **绑定** | `127.0.0.1 -::1` |

```bash
# 连接命令
redis-cli -a CHANGE_ME ping
```

### 3.3 Nginx 1.24

| 参数 | 值 |
|------|-----|
| **监听** | `0.0.0.0:80` |
| **EAP 站点配置** | `/etc/nginx/sites-enabled/eap` |
| **其他站点** | `tinybpm` (默认站点, `/etc/nginx/sites-enabled/tinybpm`) |

---

## 4. 应用服务

### 4.1 后端 (Gunicorn)

| 参数 | 值 |
|------|-----|
| **监听地址** | `0.0.0.0:5003` |
| **WSGI 服务器** | Gunicorn 23.x |
| **Worker 类型** | gevent (异步) |
| **Worker 数量** | 4 |
| **超时** | 120s |
| **进程管理** | Systemd (`eap-backend.service`) |
| **启动方式** | 随系统自动启动 |

### 4.2 前端 (Nginx 静态文件)

| 参数 | 值 |
|------|-----|
| **源文件** | `/home/wangyan/deploy/eap/frontend/dist/` |
| **访问端口** | 80（通过 Nginx） |
| **SPA 模式** | `try_files $uri /index.html` |

---

## 5. Nginx 配置

### 5.1 路由规则

```
请求路径                         → 目标
─────────────────────────────────────────────────
/                                 → 前端 SPA (静态文件)
/eap/api/*                        → 后端 Gunicorn (127.0.0.1:5003)
/eap/api/v1/chat/stream           → 后端 (禁用缓冲, chunked 传输)
/health                           → 后端健康检查
```

### 5.2 完整配置

```nginx
upstream eap_backend {
    server 127.0.0.1:5003;
}

server {
    listen 80;
    server_name 192.168.1.51;
    client_max_body_size 50M;

    root /home/wangyan/deploy/eap/frontend/dist;
    index index.html;

    location /eap/api/ {
        proxy_pass http://eap_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /eap/api/v1/chat/stream {
        proxy_pass http://eap_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        chunked_transfer_encoding on;
    }

    location /health {
        proxy_pass http://eap_backend;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 6. 环境变量

后端 `.env` 文件：`/home/wangyan/deploy/eap/backend/.env`

```bash
DEEPSEEK_API_KEY=sk-CHANGE_ME
SECRET_KEY=eap-prod-secure-key-2026
```

Systemd 注入的环境变量（在 `eap-backend.service` 中）：

```bash
FLASK_ENV=production
DATABASE_URL=postgresql://eap:CHANGE_ME@127.0.0.1:5432/eap
REDIS_URL=redis://:CHANGE_ME@127.0.0.1:6379/0
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-pro
CORS_ALLOWED_ORIGINS=http://192.168.1.51,http://192.168.1.51:3000,http://localhost:3000
```

---

## 7. 运维命令

### 7.1 后端管理

```bash
# 查看状态
sudo systemctl status eap-backend

# 启动
sudo systemctl start eap-backend

# 重启
sudo systemctl restart eap-backend

# 停止
sudo systemctl stop eap-backend

# 查看实时日志
sudo journalctl -u eap-backend -f

# 查看应用日志
tail -f /home/wangyan/deploy/eap/logs/error.log
tail -f /home/wangyan/deploy/eap/logs/access.log
```

### 7.2 Nginx 管理

```bash
# 测试配置
sudo nginx -t

# 重载配置（不中断服务）
sudo systemctl reload nginx

# 重启
sudo systemctl restart nginx
```

### 7.3 数据库管理

```bash
# 连接 PostgreSQL
psql -h 127.0.0.1 -U wangyan -d eap

# 查看表
\dt

# 备份数据库
pg_dump -h 127.0.0.1 -U wangyan eap > eap_backup_$(date +%Y%m%d).sql
```

### 7.4 Redis 管理

```bash
# 连接
redis-cli -a CHANGE_ME

# 查看所有 Key
KEYS *

# 查看 Session
KEYS session:*

# 清除所有 EAP Session
redis-cli -a CHANGE_ME KEYS "session:*" | xargs redis-cli -a CHANGE_ME DEL
```

---

## 8. 访问方式

| 入口 | URL | 说明 |
|------|-----|------|
| **前端页面** | `http://192.168.1.51` | 自动跳转登录页 |
| **API 根路径** | `http://192.168.1.51/eap/api/v1/` | 所有 API 前缀为 `/eap/api/v1/` |
| **健康检查** | `http://192.168.1.51/health` | 返回 `{"status":"ok"}` |

### 8.1 默认账号

| 角色 | 邮箱 | 密码 | 权限 |
|------|------|------|------|
| 超级管理员 | `admin@example.com` | 见 EAP_SEED_ADMIN_PW | `*:*` |
| 查看者 | `viewer@example.com` | 见 EAP_SEED_VIEWER_PW | 只读 + 对话 |

### 8.2 API 示例

```bash
# 登录
curl -X POST http://192.168.1.51/eap/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"$ADMIN_PW"}'

# 流式对话 (SSE)
curl -N -X POST http://192.168.1.51/eap/api/v1/chat/stream \
  -H "Authorization: Bearer <token>" \
  -d '{"message":"你好","thread_id":"test-001"}'

# 获取可用模型
curl http://192.168.1.51/eap/api/v1/models/available \
  -H "Authorization: Bearer <token>"
```

---

## 9. 部署步骤

### 9.1 首次部署

```bash
# 1. SSH 到服务器
ssh wangyan@192.168.1.51

# 2. 创建部署目录
mkdir -p /home/wangyan/deploy/eap/{backend,frontend/dist,logs,skills_storage}

# 3. 上传代码 (从开发机)
rsync -avz --delete \
    -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" \
    --exclude='__pycache__' --exclude='tests' \
    ./backend/ wangyan@192.168.1.51:/home/wangyan/deploy/eap/backend/

# 4. 创建虚拟环境并安装依赖
cd /home/wangyan/deploy/eap/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 5. 配置环境变量
cat > .env << EOF
DEEPSEEK_API_KEY=sk-your-key
SECRET_KEY=your-random-secret
EOF

# 6. 构建前端 (在开发机上)
cd frontend && npm run build

# 7. 上传前端构建产物
rsync -avz --delete \
    -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" \
    ./frontend/dist/ wangyan@192.168.1.51:/home/wangyan/deploy/eap/frontend/dist/

# 8. 部署 Systemd 服务
sudo cp scripts/eap-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable eap-backend
sudo systemctl start eap-backend

# 9. 部署 Nginx 配置
sudo cp scripts/nginx_eap.conf /etc/nginx/sites-enabled/eap
sudo nginx -t && sudo systemctl reload nginx

# 10. 验证
curl http://192.168.1.51/health
curl http://192.168.1.51/eap/api/v1/models/available
```

### 9.2 更新部署

```bash
# 从开发机执行 (在项目根目录):

# 1. 构建前端
cd frontend && npm run build && cd ..

# 2. 同步后端代码
rsync -avz --delete \
    -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='tests' --exclude='migrations' --exclude='.venv' \
    ./backend/ wangyan@192.168.1.51:/home/wangyan/deploy/eap/backend/

# 3. 同步前端构建产物
rsync -avz --delete \
    -e "sshpass -p '$SSH_PASSWORD' ssh -o StrictHostKeyChecking=no" \
    ./frontend/dist/ wangyan@192.168.1.51:/home/wangyan/deploy/eap/frontend/dist/

# 4. 安装新依赖 (如有)
ssh wangyan@192.168.1.51 'cd /home/wangyan/deploy/eap/backend && .venv/bin/pip install -q -r requirements.txt'

# 5. 重启后端
ssh wangyan@192.168.1.51 'sudo systemctl restart eap-backend'

# 6. 验证
curl http://192.168.1.51/health
```

### 9.3 回滚

```bash
# 如更新出现问题，回滚步骤：
# 1. 使用旧的代码重新 sync
# 2. sudo systemctl restart eap-backend
# 3. 查看错误日志: tail -100 /home/wangyan/deploy/eap/logs/error.log
```

---

## 附录 A: 端口清单

| 端口 | 服务 | 进程 |
|------|------|------|
| 22 | SSH | sshd |
| 80 | Nginx (EAP + tinybpm) | nginx |
| 5432 | PostgreSQL 16 | postgres |
| 6379 | Redis 7 (仅 localhost) | redis-server |
| 5000 | tinybpm 后端 | gunicorn |
| 5001 | tinybpm 后端 | gunicorn |
| 5002 | tinybpm 后端 | gunicorn |
| **5003** | **EAP 后端** | **gunicorn (eap-backend)** |

## 附录 B: 数据库表清单

| 表名 | 说明 |
|------|------|
| `tenants` | 租户 |
| `users` | 用户 |
| `roles` | 角色 |
| `permissions` | 权限点 |
| `user_roles` | 用户-角色关联 |
| `role_permissions` | 角色-权限关联 |
| `agent_configs` | Agent 配置 |
| `model_providers` | 模型供应商 |
| `skill_configs` | Skill 上传配置 |
| `mcp_servers` | MCP Server 配置 |
| `audit_logs` | 审计日志 |

## 附录 C: 日志文件

| 文件 | 说明 |
|------|------|
| `/home/wangyan/deploy/eap/logs/access.log` | HTTP 请求日志 |
| `/home/wangyan/deploy/eap/logs/error.log` | 应用错误 + Worker 日志 |
| `/home/wangyan/deploy/eap/logs/stdout.log` | 标准输出 |
| `/home/wangyan/deploy/eap/logs/stderr.log` | 标准错误 |
| `/var/log/nginx/access.log` | Nginx 访问日志 |
| `/var/log/nginx/error.log` | Nginx 错误日志 |
