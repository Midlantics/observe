<div align="center">
  <img src="https://a2a.midlantics.com/_next/image?url=%2Flogo.png&w=128&q=75" alt="Midlantics A2A Logo" width="120">
  <h1>Codios</h1>
  <p><strong>A2A AI Agent Security Layer — open source enforcement core</strong></p>
  <p>
    <a href="https://a2a.midlantics.com">SaaS Dashboard</a> ·
    <a href="https://a2a.midlantics.com/docs">Documentation</a> ·
    <a href="https://github.com/Midlantics/observe/issues">Issues</a>
  </p>
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/node-18%2B-green" alt="Node 18+">
</div>

# Midlantics Observe

Open-source AI agent observability and governance toolkit.

> **Cloud version** — managed hosting, billing, and enterprise features: [a2a.midlantics.com](https://a2a.midlantics.com)

## What's in this repo

| Directory | Purpose |
|-----------|---------|
| `a2a-backend/` | FastAPI backend — ingest, policy engine, approval layer, firewall, API keys |
| `sdk-python/` | Python SDK (`pip install midlantics-a2a`) |
| `sdk-js/` | JavaScript/TypeScript SDK (`npm install midlantics-a2a`) |

## Self-hosted quickstart

**Requirements:** Docker + Docker Compose

```bash
git clone https://github.com/Midlantics/observe.git
cd observe

cp a2a-backend/.env.example a2a-backend/.env
# Edit .env — set POSTGRES_PASSWORD, JWT_SECRET, RESEND_API_KEY, etc.

docker compose up -d
```

API is available at `http://localhost:8000` with full OpenAPI docs at `http://localhost:8000/docs`.

## SDK install

```bash
# Python
pip install midlantics-a2a

# JavaScript / TypeScript
npm install midlantics-a2a
```

See `sdk-python/README.md` and `sdk-js/README.md` for usage.

## Architecture

```
Agent code
  └── SDK (Python / JS)
        └── POST /ingest/traces  →  Backend (FastAPI)
                                        ├── Observe  — trace/span storage + query
                                        ├── Policy   — YAML/JSON rule evaluation
                                        ├── Approval — human-in-the-loop gate
                                        └── Firewall — real-time threat detection
```

All data lives in your PostgreSQL database (Supabase, self-hosted, or any Postgres).

## Configuration

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret to verify Supabase JWTs |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins |
| `RESEND_API_KEY` | Email for approval notifications (optional) |
| `APPROVAL_LINK_SECRET` | HMAC secret for magic-link approve/reject |
| `APP_URL` | Frontend URL (for email links) |
| `VPC_MODE` | Set `true` to enable `/docs` and relax auth |

## License

Apache 2.0
