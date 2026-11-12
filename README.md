# Hoshyar (هوشیار)

**AI brokerage command center** for multi-platform real estate in Iran — unified conversation hub, Persian intent extraction, and lead tracking so no buyer waits unanswered in WhatsApp, Divar, or DMs.

> تگ‌لاین: هوشیار — هیچ مشتری‌ای در پیام‌های بی‌پاسخ گم نمی‌شود.

## Problem

Brokerages lose revenue in **unanswered messages**, not only in closed deals: leads from Divar, WhatsApp, Instagram, and referrals sit for hours while competitors respond first.

## Solution (wedge)

1. **Unified conversation inbox** across channels brokers already use  
2. **Persian conversational NLU** — budget, neighborhood, buy vs rent, urgency  
3. **Lead SLA tracking** — who is waiting, how long, which advisor must act now  
4. **File–buyer matching signals** for managers (not just post-hoc CRM records)

## Quickstart

Requires Python 3.10+ and nothing else — no third-party Python packages, no frontend build.

Use `python3` on systems where `python` is not on the PATH.

```sh
git clone https://github.com/massoudsh/hoshyar.git
cd hoshyar
cp .env.example .env          # then set HOSHYAR_BOOTSTRAP_KEY to a random value
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # generate one
set -a; . ./.env; set +a
python3 -m hoshyar.server     # http://127.0.0.1:8000
python3 -m unittest discover -s tests -v
```

Create an office with the bootstrap key, then sign in:

```sh
curl -s localhost:8000/v1/tenants -H "X-Bootstrap-Key: $HOSHYAR_BOOTSTRAP_KEY" \
  -H 'Content-Type: application/json' -d '{"name": "املاک آفتاب"}'
```

The response contains the office `id` and an `api_key`. Use the id and either the key (manager view) or a team member's name and password (advisor view) in the web UI.

## Product one-pager

Full narrative (Persian): [`outputs/hoshyar-one-pager.md`](outputs/hoshyar-one-pager.md)

## Run with Docker

Run these from the repository root — `docker compose` reads `docker-compose.yml` from the current directory.

```sh
export HOSHYAR_BOOTSTRAP_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up --build
```

Or without Compose:

```sh
docker build -t hoshyar .
docker run -d --name hoshyar -p 127.0.0.1:8000:8000 \
  -e HOSHYAR_BOOTSTRAP_KEY="$HOSHYAR_BOOTSTRAP_KEY" \
  -v hoshyar-data:/data hoshyar
```

The image is `python:3.12-slim` with no third-party packages, runs as UID 10001, and keeps state in the `/data` volume (`HOSHYAR_DATABASE_PATH=/data/hoshyar.sqlite3`). It listens on `0.0.0.0:8000` inside the container; Compose publishes it on loopback only, so put a TLS-terminating proxy in front before exposing it. The container handles `SIGTERM` and shuts down cleanly, and its `HEALTHCHECK` calls `/health`.

CI builds the image on every push, starts it, and checks the health endpoint, the frontend, office creation, the persisted database file and the unprivileged user id.

## Architecture

[`ARCHITECTURE.md`](ARCHITECTURE.md) documents the data flow, layer boundaries, consistency model and threat model.

## Current implementation

Application code lives in this repository:

- [`hoshyar/`](hoshyar/) — Python domain services, rule-based Persian intent extraction, SQLite persistence, and an HTTP API.
- [`frontend/`](frontend/) — a Persian RTL interface served by the Python server, using plain HTML, CSS, and JavaScript.
- [`Dockerfile`](Dockerfile) / [`docker-compose.yml`](docker-compose.yml) — a hardened image and a one-command local stack.
- [`tests/`](tests/) — standard-library `unittest` coverage for services, API authentication and tenant isolation, channel ingestion, and HTTP endpoints.

The prototype includes member sessions and role-aware views, lead assignment and follow-up queues, listing management, and explained lead–listing matches. Channel adapters normalize Telegram, WhatsApp, Divar, and Sheypoor payloads behind authenticated webhook endpoints; configuring providers and production deployment remains separate work.

### Run locally

Requires Python 3.10 or newer; no third-party Python packages or frontend build step are required. Set `HOSHYAR_BOOTSTRAP_KEY` to a private value in your environment before starting the server. It authorizes office creation and must not be committed or exposed in frontend code.

From the repository root:

```sh
python3 -m hoshyar.server
```

The server binds to `127.0.0.1:8000` and serves both the frontend and API. `GET /health` is an unauthenticated health check. SQLite data defaults to `hoshyar.sqlite3`; set `HOSHYAR_DATABASE_PATH` to override its location. The current prototype is not a production deployment.

### Configuration

All settings are environment variables; see [`.env.example`](.env.example).

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `HOSHYAR_BOOTSTRAP_KEY` | yes | — | Authorizes office creation |
| `HOSHYAR_DATABASE_PATH` | no | `hoshyar.sqlite3` | SQLite file |
| `HOSHYAR_HOST` / `HOSHYAR_PORT` | no | `127.0.0.1` / `8000` | Bind address |
| `HOSHYAR_LOG_LEVEL` | no | `info` | `debug`, `info`, `warning`, `error` |

### Run tests

```sh
python3 -m unittest discover -s tests -v
```

The suite covers the domain service, SQLite persistence, API authentication and tenant isolation, channel webhooks, HTTP endpoints and a golden-set regression check for Persian intent extraction.

## Security

- **Tenant isolation:** every domain read and write validates that the lead, agent or listing belongs to the authenticated tenant; cross-tenant access raises before any mutation.
- **Credentials at rest:** office API keys and session tokens are SHA-256 digests; member passwords are PBKDF2-SHA256 (200 000 rounds, per-user salt). Nothing is compared with `==`.
- **Roles:** an advisor sees only their assigned leads and cannot manage the team, listings or channel secrets; those actions require a manager session or the office key.
- **Channel webhooks:** each channel gets its own secret, hashed at rest, supplied in `X-Channel-Secret`; deliveries are deduplicated by provider message id.
- **Request handling:** 1 MB body cap, rejected `Transfer-Encoding` and malformed lengths, `nosniff` on responses, `no-store` on JSON.
- **Secrets hygiene:** `.env` is gitignored, [`.env.example`](.env.example) lists every variable with no real values, and `gitleaks` runs on every push and pull request.

Known gaps are listed in the threat model: no TLS termination, no rate limiting, no provider signature verification, passwords optional, sessions never expire, and SQLite is a single-process store.

## Quality gates

CI (`.github/workflows/ci.yml`) byte-compiles the package, runs the full test suite, syntax-checks the frontend, scans for committed secrets with gitleaks and publishes a CycloneDX SBOM. CodeQL runs on `main` and weekly; Dependabot watches pip and GitHub Actions.

## Persian intent evaluation

The rule-based extractor is scored against a checked-in golden set, [`outputs/evals/intent-golden.json`](outputs/evals/intent-golden.json), by `tests/test_intent_eval.py`. Purpose accuracy and per-field accuracy must stay above the thresholds in that file, so a change that regresses extraction fails CI instead of degrading silently. The set covers buy/rent/sell phrasing, Persian and Arabic digits, رهن and اجاره separation, neighborhoods and urgency.

This is a regression gate over hand-written cases, **not** evidence of accuracy on real office conversations.

## Suggested stack (future roadmap, not implemented)

| Layer | Proposed direction |
| --- | --- |
| Ingestion | Webhooks + queue (Redis/BullMQ or SQS); idempotent message IDs per channel |
| NLU | Fine-tuned small model or structured extraction via **JSON schema** + validator; eval set of real Farsi chat snippets |
| Routing | [Routapse](https://github.com/massoudsh/Routapse) for cheap triage vs heavy reasoning |
| Storage | Postgres + pgvector for lead/file similarity; audit log for compliance |
| Observability | OpenTelemetry traces on ingestion → intent → assignment |
| Frontend | Next.js App Router + RTL; real-time inbox (SSE or WebSocket) |

## Status

A runnable prototype is implemented in this repository; production hardening and validation with real offices remain future work. The proposed stack above is a roadmap, not a description of the current runtime. Track build-out via GitHub Issues on this repository.

## License

See [LICENSE](LICENSE).
