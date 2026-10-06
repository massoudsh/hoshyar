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

## Suggested stack (implementation roadmap)

| Layer | SOTA direction |
| --- | --- |
| Ingestion | Webhooks + queue (Redis/BullMQ or SQS); idempotent message IDs per channel |
| NLU | Fine-tuned small model or structured extraction via **JSON schema** + validator; eval set of real Farsi chat snippets |
| Routing | [Routapse](https://github.com/massoudsh/Routapse) for cheap triage vs heavy reasoning |
| Storage | Postgres + pgvector for lead/file similarity; audit log for compliance |
| Observability | OpenTelemetry traces on ingestion → intent → assignment |
| Frontend | Next.js App Router + RTL; real-time inbox (SSE or WebSocket) |

## Status

Early product definition and GTM materials. Application code lives in sibling repos as the portfolio evolves — track build-out via GitHub Issues on this repository.

## License

See [LICENSE](LICENSE).
