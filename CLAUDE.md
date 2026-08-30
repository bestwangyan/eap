# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EAP (Enterprise Agent Platform) is a BS-architecture multi-tenant AI agent platform. Flask + React + LangGraph, deployed on `192.168.1.51` under `/home/wangyan/deploy/eap`.

## Common Commands

### Local Development

```bash
make dev-backend      # Start Flask on :5000 (needs PG/Redis on 192.168.1.51)
make dev-frontend     # Start Vite dev server on :3000 (proxies /eap → :5000)
make install          # Install Python + Node dependencies
```

### Deployment

```bash
make deploy           # Build frontend + sync backend + restart (full deploy)
make deploy-backend   # Sync backend only + restart
make deploy-frontend  # Build & sync frontend only
make deploy-nginx     # Update Nginx config on server
make deploy-restart   # Restart backend on server
make server-info      # Check server status, ports, disk
```

### Frontend

```bash
cd frontend && npm run dev     # Dev server with HMR
cd frontend && npm run build   # Production build to dist/
```

### Server Ops

```bash
ssh wangyan@192.168.1.51
sudo systemctl status eap-backend
sudo systemctl restart eap-backend
tail -f /home/wangyan/deploy/eap/logs/error.log
```

## Architecture

### Request Flow

```
Browser → Nginx(:80) → /eap/ → frontend static files (SPA fallback)
                      → /eap/api/* → Gunicorn(:5003) → Flask → LangGraph Agent
                      → /health → Gunicorn(:5003)
```

The frontend React app uses `<BrowserRouter basename="/eap">` and Vite `base: '/eap/'`. All API calls go through `/eap/api/v1/*`.

### Key Patterns

**Auth**: JWT (only `sub` + `jti`) + Redis Session. Permissions/roles/tenant context live in Redis (`session:{user_id}:{jti}`), NOT in JWT claims. This enables instant permission revocation and forced logout. Middleware is at `app/middleware/auth.py` — `load_user_context()` decorates endpoints, `require_permission(codename)` enforces RBAC.

**RBAC**: User → Role → Permission (codename format: `resource:action`, e.g. `agent:create`). Preset roles seeded at startup: SuperAdmin (`*:*`), TenantAdmin, Developer, Viewer. Permissions come from Redis session, refreshed on role change via `SessionManager.update_user_permissions()`.

**Multi-tenancy**: DB queries always filtered by `tenant_id` from `g` object. LangGraph thread IDs are `{tenant_slug}:{user_id}:{uuid}`.

**Agent**: `app/core/agent/deep_agent_factory.py` — 基于 deepagents 的编排核心：
create_deep_agent 组装（skills 渐进披露 / subagents / memory / backend 沙箱），
后端双实现（FilesystemBackend local / DockerBackend container），
HITL 通过 interrupt_on + ApprovalRequest 审批流转。模型选择动态解析
（聊天页 > 智能体绑定 > 租户默认），图按指纹缓存。

**Seed Data**: On first startup, `_init_db()` auto-creates default tenant, admin/viewer users, preset roles/permissions, and seeds `ModelProvider.seed_defaults()` from env vars.

### Server Infrastructure

| Service | Port | Credentials |
|---------|------|-------------|
| PostgreSQL 16 + pgvector | 5432 | 凭据见服务器 .env |
| Redis 7 | 6379 (localhost only) | 凭据见服务器 .env |
| EAP Gunicorn | 5003 | systemd: `eap-backend` |
| Nginx | 80 | config: `/etc/nginx/sites-enabled/eap` |
