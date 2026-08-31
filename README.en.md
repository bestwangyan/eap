# EAP — Enterprise Agent Platform

> Multi-tenant AI agent platform · B/S architecture · On-premises deployment
>
> [:cn: 中文](README.md)

EAP (Enterprise Agent Platform) is a multi-tenant AI agent platform for enterprises. Users create agents on the platform, configure model providers, tools, knowledge bases, skills, and sub-agents for them, and chat with them in the browser via streaming responses. The platform provides RBAC permissions, tenant data isolation, security guardrails, container-sandboxed execution, human-in-the-loop (HITL) approvals, and end-to-end call tracing.

## Key Features

- **Multi-tenant isolation**: all DB queries filtered by `tenant_id`; chat thread IDs follow `{tenant_slug}:{user_id}:{uuid}`; execution sandboxes isolated per tenant/user/thread directory
- **RBAC**: User → Role → Permission (encoded as `resource:action`); JWT + Redis sessions with instant permission revocation and forced logout
- **Streaming chat**: token-by-token SSE output with full tool-call visualization (localized aliases, arguments, results)
- **Model providers**: unified integration of DeepSeek / OpenAI / Anthropic / LM Studio; platform-level and per-agent model binding with runtime API key resolution
- **Agent capabilities**: built-in tools (calculator, datetime, web search, knowledge-base retrieval, memory access) + deepagents default tools (task planning, file read/write, grep/glob) + external MCP tools
- **Knowledge base & RAG**: document upload and parsing (PDF / DOCX / TXT), tokenized search for Chinese and English, collection-level authorization
- **Two-tier memory**: global memory (DB-persisted, high-importance entries auto-injected into the system prompt) + per-session memory files
- **Skills & sub-agents**: prompt-mode skills with progressive disclosure; agent-mode skills / sub-agents with isolated contexts and optionally independent models
- **Secure execution backends**: `local` (no-shell file sandbox) / `container` (disposable Docker containers: no network, memory-capped, `--cap-drop ALL`, fail-closed)
- **Human-in-the-loop (HITL)**: configurable human approval for file write / edit / shell execution; in-chat approval cards with approve / reject / edit-and-approve, then automatic resume of the stream
- **Security guardrails**: PII redaction (Presidio) + content safety checks on both input and output
- **Full-stack observability**: traces, token usage, and cost records (LangSmith-compatible + OpenTelemetry)

## System Architecture

```
Browser ──▶ Nginx(:80) ── /eap/* ────────▶ React SPA static assets
              │
              └── /eap/api/* ──▶ Gunicorn(:5003) ──▶ Flask ──▶ deepagents orchestration core
                                                             │
        ┌────────────────────────────────────────────────────┼──────────────────────────┐
        │                                                    │                          │
  PostgreSQL 16 + pgvector                          Redis 7 (sessions / permissions)   Docker (container sandbox)
  (business data / KB vectors / checkpoints)        (localhost only)                   disposable, --network none
```

- **Frontend**: React 18 + Ant Design 5 + Vite, served under the `/eap` prefix, SSE streaming rendering
- **Backend**: Flask 3 + deepagents (LangGraph), dual-stream mode (`messages` for tokens + `updates` for complete tool arguments)
- **Orchestration core**: DeepAgentFactory assembles a deepagents graph from the agent configuration (model / tools / skills / sub-agents / execution backend); compiled graphs are LRU-cached; PostgresSaver checkpoints persist state for resumable conversations
- **Interrupt & resume**: LangGraph interrupt → approval persisted to DB → resume continues streaming after the decision

## Project Structure

```
backend/             Flask backend
  app/api/v1/        REST + SSE endpoints (chat / agent / workflow / knowledge …)
  app/core/agent/    deepagents orchestration core (factory / orchestrator / backends / tools)
  app/core/guardrails/  Security guardrails (PII redaction + content safety)
  app/models/        Data models
frontend/            React frontend (Vite + AntD + zustand)
scripts/             Ops & test scripts (eap_full_test.sh regression suite, etc.)
docs/superpowers/    Design specs and implementation plans
skills/              Platform-level skill directory
mcp_servers/         MCP server configurations
docker-compose.yml   Local infrastructure (PostgreSQL / Redis)
```

## Quick Start

### Prerequisites

- Python 3.11+, Node.js 18+
- PostgreSQL 16 + pgvector and Redis 7 (spin them up locally via `docker-compose.yml`, or reuse the dev server instances)

### Install & Run

```bash
make install        # Install Python + Node dependencies
make dev-backend    # Flask dev server on :5000 (requires access to PG/Redis)
make dev-frontend   # Vite dev server on :3000 (proxies /eap → :5000)
```

On first startup the database is initialized automatically: default tenant, admin / viewer users, preset roles and permissions, and model-provider seed data.

Open http://localhost:3000/eap

### Configuration

Copy `.env.example` to `backend/.env` and configure the database / Redis connections and model API keys.

## Deployment

Production stack: Nginx + Gunicorn + PostgreSQL + Redis + Docker, deployed on an on-premises server.

```bash
make deploy            # Build frontend + sync backend + restart (full deploy)
make deploy-backend    # Backend only
make deploy-frontend   # Frontend only
make server-info       # Server status / ports / disk check
```

## Testing

```bash
bash scripts/eap_full_test.sh
```

Deployment-level integration regression suite: 93 checks covering auth / RBAC / agent CRUD / tools / memory / skills / sub-agents / knowledge-base RAG / security guardrails / HITL / observability.

## Design Documents

- deepagents orchestration redesign: [docs/superpowers/specs/2026-08-30-deepagents-orchestration-design.md](docs/superpowers/specs/2026-08-30-deepagents-orchestration-design.md)
- Implementation plan: [docs/superpowers/plans/2026-08-30-deepagents-orchestration.md](docs/superpowers/plans/2026-08-30-deepagents-orchestration.md)
