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

## Product one-pager

Full narrative (Persian): [`outputs/hoshyar-one-pager.md`](outputs/hoshyar-one-pager.md)

## Current implementation

Application code lives in this repository:

- [`hoshyar/`](hoshyar/) — Python domain services, rule-based Persian intent extraction, SQLite persistence, and an HTTP API.
- [`frontend/`](frontend/) — a Persian RTL interface served by the Python server, using plain HTML, CSS, and JavaScript.
- [`tests/`](tests/) — standard-library `unittest` coverage for services, API authentication and tenant isolation, channel ingestion, and HTTP endpoints.

The prototype includes member sessions and role-aware views, lead assignment and follow-up queues, listing management, and explained lead–listing matches. Channel adapters normalize Telegram, WhatsApp, Divar, and Sheypoor payloads behind authenticated webhook endpoints; configuring providers and production deployment remains separate work.

### Run locally

Requires Python 3.10 or newer; no third-party Python packages or frontend build step are required. Set `HOSHYAR_BOOTSTRAP_KEY` to a private value in your environment before starting the server. It authorizes office creation and must not be committed or exposed in frontend code.

From the repository root:

```sh
python -m hoshyar.server
```

The server binds to `127.0.0.1:8000` and serves both the frontend and API. `GET /health` is an unauthenticated health check. SQLite data defaults to `hoshyar.sqlite3`; set `HOSHYAR_DATABASE_PATH` to override its location. The current prototype is not a production deployment.

### Run tests

```sh
python -m unittest discover -s tests -v
```

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
