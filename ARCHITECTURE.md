# Architecture

Hoshyar is a small, dependency-free prototype: a Python standard-library HTTP server that serves both a JSON API and a Persian RTL single-page frontend, backed by SQLite.

## Data flow

```mermaid
flowchart LR
    subgraph Channels
        TG[Telegram]
        WA[WhatsApp]
        DV[Divar / Sheypoor]
        SMS[SMS]
        MAN[Manual entry]
    end

    TG -->|POST /v1/channels/{tenant}/telegram<br/>X-Channel-Secret| HOOK[channels.normalize]
    WA -->|same shape| HOOK
    DV -->|same shape| HOOK
    SMS -->|same shape| HOOK
    MAN -->|POST /v1/tenants/{tenant}/messages| API

    HOOK -->|contact, body, name, sent_at, external_id| API[api.HoshyarApi]
    API --> SVC[service.HoshyarService]
    SVC --> INTENT[intent.extract_intent / merge_intent]
    SVC -->|leads, listings, agents, followups| API
    API <-->|load / save snapshot, keys, sessions, deliveries| DB[(SQLite)]
    API -->|JSON| UI[frontend/ RTL SPA]
    UI -->|fetch with X-Session-Token or X-API-Key| API
```

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Transport | `hoshyar/server.py` | HTTP verbs, 1 MB body cap, framing checks, static assets, request logging |
| API | `hoshyar/api.py` | Routing, authentication, roles, JSON serialization, channel secrets |
| Channel adapters | `hoshyar/channels.py` | Per-provider payload normalization, delivery ids |
| Domain | `hoshyar/service.py`, `hoshyar/intent.py`, `hoshyar/models.py` | Tenants, leads, messages, listings, matching, follow-ups, measurement |
| Persistence | `hoshyar/store.py` | One JSON snapshot in SQLite plus auxiliary tables, `BEGIN IMMEDIATE` transactions |
| Observability | `hoshyar/telemetry.py` | One JSON log line per event with a per-request id |
| UI | `frontend/` | Vanilla HTML/CSS/JS, no build step |

## Data model

- One `Tenant` per office. Every domain lookup goes through `_tenant` / `_agent` / `_lead` / `_listing`, which reject cross-tenant ids.
- `Lead` is keyed by contact within a tenant, so one buyer across WhatsApp and Telegram is one lead with many `Message`s.
- `Intent` is produced by a rule-based extractor and merged across inbound messages; `price` is for sales, `deposit`/`rent` for rentals.
- `Listing` carries `deal_type` and is only matched against the same deal type; a known budget is a hard filter, not a score bonus.

## Consistency and concurrency

Writes run inside `SqliteStore.transaction()`, which takes `BEGIN IMMEDIATE` on a per-thread connection, so read-modify-write of the whole snapshot cannot interleave between requests. A single server process is assumed: there is no advisory lock across processes, no snapshot versioning and no migration framework.

## Security model (threat model)

Assets: office lead data, member credentials, channel secrets, the bootstrap key.

| Threat | Control | Residual risk |
| --- | --- | --- |
| Cross-tenant data access | Every domain method validates tenant ownership; API key and session token map to exactly one tenant | A bug in a new endpoint that skips `_tenant` validation |
| Stolen office key | Keys are stored as SHA-256 digests and compared with `hmac.compare_digest` | Keys never expire; rotation is manual |
| Impersonating a colleague | Members can carry a PBKDF2-SHA256 password (200k rounds, per-user salt) | Password is optional; a member without one signs in by name alone |
| Forged channel webhook | Per-channel secret, hashed at rest, required in `X-Channel-Secret` | No provider signature verification (e.g. Meta's `X-Hub-Signature-256`) yet |
| Replayed channel message | `channel_deliveries` keyed by `(tenant, channel, external_id)` | Providers that omit an id cannot be deduplicated |
| Oversized or malformed request | 1 MB cap, negative/absent length rejected, `Transfer-Encoding` rejected, JSON object enforced | No per-client rate limiting |
| Malicious message content | Frontend renders with `textContent` only; no `innerHTML` | Persian text is stored verbatim; no content moderation |
| Secret leakage in logs or repo | Logs never include headers or bodies; gitleaks runs in CI; `.env` is gitignored | Local `.env` discipline remains a human responsibility |
| XSS via static assets | `X-Content-Type-Options: nosniff`, JSON responses `Cache-Control: no-store` | No CSP header yet |

Not in scope for the prototype: TLS termination, WAF, audit trail, data retention policy, encryption at rest.

## What is deliberately absent

- No outbound channel delivery: advisors reply in their own apps, Hoshyar only records.
- No LLM in the loop: intent extraction is rules, measured by `outputs/evals/intent-golden.json`.
- No background workers: follow-up buckets and staleness are computed on read.
- No OpenTelemetry exporter: structured JSON logs are emitted, but no trace backend is wired.
