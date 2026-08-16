# massoudsh GitHub Portfolio — Task Backlog for CLI AI

Generated 2026-08-16 from analysis of all 44 repos (17 deep-dived, 27 swept).
Each task: what to do, which files, and a done-when check. Work top-down within a repo.
Repos are independent — tasks can be executed in any repo order. Priorities:

- **P0** = security leak or user-visible breakage
- **P1** = CI/test debt that blocks safe development
- **P2** = repo hygiene (junk, licenses, README accuracy)
- **P3** = features & polish

---

## P0 — URGENT (do these first)

### [P0-1] Findash — remove committed secrets from public repo
- Repo: `massoudsh/Findash` (PUBLIC)
- `env.local` at repo root contains real `SECRET_KEY` and `JWT_SECRET_KEY` values (plus `DB_PASSWORD=SecurePostgres2025!`).
- Actions: `git rm env.local`, ensure `.gitignore` covers `.env*`/`env.local`, remove the file from git history (`git filter-repo` or BFG), add a gitleaks step to CI.
- Done when: `git log --all -- env.local` is empty, gitleaks passes, and README security note tells users to rotate the leaked keys (rotation itself is a human action).

### [P0-2] sabzina — production build ships with no CSS (Tailwind broken)
- Repo: `massoudsh/sabzina` (private, Next.js)
- `web/src/app/globals.css` uses Tailwind v4 `@import "tailwindcss"` but there is no `postcss.config.*`, no `@tailwindcss/postcss` package, and the v3-style `web/tailwind.config.ts` (custom `sabzina` palette, keyframes) is ignored by v4. `npm run build` succeeds but emits ~2.6KB of CSS — zero utilities. 135 usages of `sabzina-*` classes are dead; the entire UI renders unstyled.
- Actions: add `@tailwindcss/postcss` devDep, create `web/postcss.config.mjs`, port palette/keyframes into an `@theme` block in `globals.css`.
- Done when: built CSS contains `.flex`, `bg-sabzina-50` (with `#f0fdf4`), `animate-fade-in` and exceeds 100KB.

### [P0-3] Findash — CI is decorative: tests can never fail
- `.github/workflows/ci-cd.yml` has `flake8/black/isort/mypy ... || true`, and the pytest step ends in `|| true`. Commit history shows `pytest failed (exit 1)` on main while CI stayed green.
- Actions: remove every `|| true`; delete lint steps the codebase can't pass rather than keeping fake-green ones; keep `pytest` strict.
- Done when: workflow YAML contains no `|| true`, and a deliberately broken test on a scratch branch fails the job.

### [P0-4] Findash — documented default credentials in seeds
- `database/seeds/01_default_users.sql` inserts admin with bcrypt hash and comment `-- password: admin123`.
- Actions: rewrite seeds to take credentials from environment/psql variables and fail when unset; strip password comments.
- Done when: `grep -ri "admin123\|bcrypt" database/seeds/` returns 0 hits.

### [P0-5] Didebaan — CI red on every push; tests never run
- Repo: `massoudsh/Didebaan` (public, Django)
- flake8 `W391` (trailing blank lines) in `backend/config/wsgi.py:12` and `backend/manage.py:23` fail the lint step, so migrate/test steps are skipped on every run. README claims "CI ✅".
- Also fake deploy-check: `manage.py check --deploy` receives `SECRET_KEY=... ALLOWED_HOSTS=...` as positional CLI args instead of env vars, always errors, and silently falls back to plain `check`.
- Actions: fix blank lines, run flake8 locally until clean; move env vars into step `env:` and delete the fallback.
- Done when: pushed CI run reaches and passes "Run tests"; deploy check runs with no fallback branch.

### [P0-6] sabzina — CI workflow belongs to a different project
- `.github/workflows/ci-cd.yml` is "Trading Platform CI/CD": installs nonexistent Python `requirements.txt`, pytests nonexistent `src/`, builds nonexistent `Dockerfile.fastapi`, deploys to AWS ECS `trading-service`. Fails every push.
- Actions: replace with a Node pipeline: `cd web && npm ci && npm run lint && npx tsc --noEmit && npx jest && npm run build` (install `eslint` + `eslint-config-next` first — currently missing while a `lint` script exists).
- Done when: push to main produces a green run executing all steps.

---

## P1 — CI & test debt

### [P1-1] catalogueyar — README undersells working code
- README "وضعیت فعلی" claims pipeline raises `NotImplementedError`/501, but `backend/app/pipeline/vision.py`, `speech.py`, `generate.py` contain complete OpenAI implementations and `backend/app/api/catalog.py` maps errors to 503/502.
- Action: rewrite the status section to match actual behavior.
- Done when: no mention of `NotImplementedError` remains and error codes match the code.

### [P1-2] catalogueyar — add tests + CI + upload hardening
- No tests, no `.github/`. Uploads: `_write_temp` writes any file with no content-type check or size cap.
- Actions: (a) pytest suite with mocked OpenAI client covering 0/>5 images → 400, 503 without key, merge logic; (b) `.github/workflows/ci.yml`; (c) validate `content_type` starts with `image/`, reject >10MB per file, check audio suffixes.
- Done when: ≥8 tests pass with no network calls; CI green on main; non-image/oversized uploads rejected with 400.

### [P1-3] vafa-copilot — engine has zero tests (most complex logic of the batch)
- `mvp/engine/next_best_action.py` (347 LOC, 9 prioritized action branches) is untested.
- Actions: `mvp/tests/test_engine.py` covering all 9 action types + edge cases (do_not_disturb wins; no opt-in → channel "none"); add CI workflow (Python 3.11/3.12 + pytest).
- Done when: `python3 -m pytest mvp/tests/` passes and CI is green on master.

### [P1-4] vafa-copilot — frozen clock
- `TODAY = date(2026, 7, 24)` hardcoded in the engine; decisions silently rot.
- Actions: replace with `date.today()` overridable via `VAFA_TODAY` env var; pin date in tests via env var.
- Done when: engine works with real today and tests are deterministic.

### [P1-5] nabz — wire CI + close well-scoped open issues
- 12 passing tests exist but no CI (issue #9 acknowledges). In-memory feedback store (issue #4), no batch endpoint (#8), no auth (#7).
- Actions: (a) CI running `pytest services/nba-engine/tests/`; (b) `POST /decide/batch` accepting `list[Customer]` returning `list[Decision]` + tests; (c) optional API-key auth via `NABZ_API_KEY` env (401 only when set) + tests for both modes; (d) persist feedback to SQLite keeping function signatures.
- Done when: CI green; batch endpoint tested for empty list/mixed personas/validation errors; feedback survives re-instantiation.

### [P1-6] vamgar — finish packaging + CI
- `pyproject.toml` is a stub (no `[project]`, not installable); no CI despite 15 passing tests.
- Actions: complete `[project]` metadata + build backend so `pip install -e .` works; add CI (pytest + ruff); add edge-case tests for `cashflow.py` (single transaction, gap-at-start, duplicate timestamps, credit-limit-under-covers-gap in `engine.py`).
- Done when: `pip install -e . && python -c "import vamgar"` succeeds; CI green; edge branches covered.

### [P1-7] sudban — test the 7 financial engines
- Zero tests, no `test` script, no CI. `src/services/*.ts` (marginCalculator, priceSuggestionEngine, riskAlertEngine, wisdomEngine, salesTrend, competitivePosition, scenarioSimulator) are financial decision logic.
- Actions: add vitest, `"test": "vitest run"`, unit tests per engine (floor formula throws when returnRate≥1 or commission+minMargin≥1; anchor modes; LOSS_MAKING vs LOW_MARGIN exclusivity); add CI (Node 20, `npm ci && npm run build && npm test` — engines are pure, no DB needed).
- Done when: ≥25 assertions pass; CI green on main.

### [P1-8] pishbin — repair broken frontend test tooling
- `frontend/jest.config.mjs` + a test file exist, but `frontend/package.json` has no `test` script and no jest devDependencies. README instructs `npm test` → fails.
- Actions: add script + `jest`, `jest-environment-jsdom`, `@types/jest`; add CI (backend: Python 3.11 + pytest with SQLite in-memory conftest; frontend: Node 20 + lint + test).
- Done when: `npm test` exits 0 in `frontend/`; CI green.

### [P1-9] TabibYar — orphaned submodule + CI
- `.gitmodules` declares submodule `RA3G-Agent` but no gitlink exists in the tree.
- Actions: delete `.gitmodules` (or properly `git submodule add`); add CI: Node job (`cd app && npm ci && npm test` — 6 test files, mock-based) + Python smoke (`py_compile stt-service/server.py`, avoid torch install).
- Done when: `git submodule status` clean on fresh clone; CI green.

### [P1-10] sakhtban — CI + lint tooling
- 9 pure-unit test files, no CI. `frontend` has `"lint": "next lint"` but no eslint packages → fails on fresh clone.
- Actions: CI with three jobs (backend pytest, frontend build, mobile typecheck); add `eslint` + `eslint-config-next` or remove the lint script; add `backend/Dockerfile` + root `docker-compose.yml` (api + postgres 16, healthcheck).
- Done when: all CI jobs green; `npm run lint` exits 0 non-interactively; `docker compose config` validates.

### [P1-11] mizan-legal-copilot — CI + tests + upload guard
- 2 tests exist, never run in CI (no `.github/`). Upload handler buffers the full body before the 15MB check in `backend/app/main.py`.
- Actions: (a) CI (Python 3.11 + pytest); (b) `test_api.py` (401/400/413/422/200 paths) + `test_document_parser.py`; (c) reject on `Content-Length`/`file.size` before `await file.read()`; (d) add Dockerfile + compose with `/health` check; (e) `backend/requirements-dev.txt`.
- Done when: ≥10 tests pass; oversized declared length rejected without reading body; `docker compose up` serves `/health` → 200.

### [P1-12] shemronkebab — fix broken e2e toolchain + expand tests
- `playwright.config.ts` + 2 e2e specs exist but `@playwright/test` is not in devDependencies. Only 2 jest files vs a large `app/api/` surface.
- Actions: add `@playwright/test`; add jest suites for `app/api/payment`, `reservation`, `contact`, `table-order` error paths.
- Done when: fresh clone runs `npm run test:e2e` with no global playwright; jest covers every route dir under `app/api/`.

### [P1-13] Hamgam — CI + auth scaffold
- Cleanest repo (30 vitest tests incl. tenant isolation via pg-mem) but zero CI; auth not implemented (`sellerId` passed raw, documented).
- Actions: (a) CI: backend (`npm ci && npm run typecheck && npm test`) + frontend (`+ npm run build`); (b) JWT login + middleware guarding `/api/*`, keep demo mode behind a flag, update tenant-isolation tests for authenticated sessions.
- Done when: CI green; all existing + new auth tests pass.

### [P1-14] negotia — implement the real OpenAI provider
- `src/llm/provider.js` documents `LLM_PROVIDER=openai` + `createOpenAiProvider()`, but that function doesn't exist — every non-mock value throws. The README's "AI" claim rests on a keyword mock.
- Actions: implement `createOpenAiProvider()` (chat completions, JSON output for `summarize` → `{summary, intent, seriousness}`), wire into `getLlmProvider()`, clear error when key missing.
- Done when: existing tests pass with mock; new test with fake fetch verifies summarize mapping; `LLM_PROVIDER=openai` no longer throws unconditionally.

### [P1-15] Didebaan — repo bloat + EOL Django + license contradiction
- 16.9MB CSV at `دیتاست-صرفا برای برخی چالش‌ها/...` dominates this public repo, no provenance/license documented. `Django==4.2.7` is past EOL (April 2026). Public repo with no LICENSE while `SPECTACULAR_SETTINGS` says Proprietary.
- Actions: (a) purge dataset path from history (filter-repo), add `.gitignore` entry, add `DATA.md` with provenance + preview script; (b) bump Django to 5.x LTS + compatible DRF/django-filter, run tests; (c) add LICENSE + align README and SPECTACULAR_SETTINGS; (d) fix `Makefile setup-iran` `createsuperuser --noinput || true` to env-driven, failing loudly.
- Done when: fresh clone shrinks ~3x; tests pass on new Django; repo reports a license; `make setup-iran` fails clearly without credentials.

---

## P2 — Hygiene: junk eviction, licenses, README fixes

### [P2-1] Findash — purge committed junk & de-Octopus
- Remove from tree + gitignore: `uploads/` (4 screenshots), `dataset/` (ML plot PNGs), `MyProjects/` (nested foreign repo), `.cursor/`, root `__init__.py`.
- README hero image points to `frontend-nextjs/public/logo.png` which does not exist (only `octopus-*.jpg` files) — fix or commit a real logo.
- Rebrand active (non-archive) files: `docker-compose-core.yml` image names `octopus-trading-*` + hardcoded `SECRET_KEY=docker-dev-secret-key...`; `Makefile` `PROJECT_NAME := octopus-trading-platform`; `config/api_keys_config.py` header says "never commit" while committed.
- Done when: `git ls-files` shows none of the junk paths; README image URL returns 200; `grep -ril octopus` over non-archive paths returns 0.

### [P2-2] bartakht — orphaned gitlinks + personal data
- `repos/Findash`, `repos/RA3G-Agent`, `repos/mizan-legal-copilot`, `repos/pishbin`, `repos/sabzina`, `repos/shemronkebab` are commit-type entries with NO `.gitmodules` — clones get empty dirs and these names leak private-project names. Also `uploads/` has personal-named spreadsheet + screenshots, `outputs/` has generated decks/reports. No CI, no LICENSE.
- Actions: `git rm --cached repos/*` (or author `.gitmodules` if intentional — ask owner); purge `uploads/`/`outputs/`; add LICENSE; add CI (app: `npm ci && npm test`; web: `npm ci && npm run build`).
- Done when: `git ls-files repos/ uploads/ outputs/` empty; fresh clone has no phantom dirs; CI green.

### [P2-3] shemronkebab — root doc sprawl + license contradiction + dep hygiene
- 17 status/guide `.md` files + `DATABASE_SCHEMA.sql` at root (4 overlapping "production" docs, 3 overlapping "summaries"). LICENSE is Apache-2.0 but README says MIT. `next@14.2.5` has known CVEs (14.2.35 is last 14.2.x patch). `sqlite3` dep leftover alongside Prisma. `.env` tracked though gitignored (contains only harmless dev SQLite path).
- Actions: consolidate docs into `docs/` with an index, delete pure session-noise files; `git rm --cached .env`; align README license to Apache-2.0; bump next, remove sqlite3 if unused; README "future improvements" lists DB/auth as TODO though they exist.
- Done when: root has only README + LICENSE (plus config files); `git ls-files | grep -x .env` empty; build/lint/test pass.

### [P2-4] shed57 — apply pending CI diff + asset diet + de-template
- `docs/CI-WORKFLOW-PENDING.md` holds a ready diff for `ci.yml` (workflow_dispatch + smoke test) that couldn't be pushed for token scope — apply it, delete the doc.
- 55MB repo: `public/audio/rastegari.mp3` is 31.4MB; project JPGs 2–4MB each (a `scripts/optimize-images.ts` exists but was never applied); `uploads/` committed with screenshots + pasted-text files (not gitignored).
- Template leftovers: `package.json` name is still `astro-theme-pure`, `README-zh-CN.md`, vendored `packages/pure/` + `preset/` duplicating the `astro-pure` npm dep.
- Done when: pending doc gone and ci.yml has workflow_dispatch; `git ls-files uploads/` empty; binaries compressed (mp3 → ~3–5MB) and build still green; package renamed `shed57`. (History rewrite to actually shrink clones needs owner sign-off.)

### [P2-5] sabzina — cross-project artifacts + durable storage + config hardening
- Delete `outputs/noqte-knowledge.tar.gz` (446KB, another product's wiki) and `uploads/Screenshot-*.png`; remove prisma scripts from `web/package.json` (no prisma dep/schema exists); clean Noqte references from `.gitignore`.
- `serverOrderStore.ts` and `otpStore.ts` are in-memory Maps — orders/payments lost on restart. Back with Redis TTL keys or Prisma+SQLite, keep Map as dev fallback.
- Add `web/next.config.ts` (security headers, `poweredByHeader: false`); flip `tsconfig strict: true` and fix errors.
- Done when: junk paths untracked; restarting the server preserves an order and the Zarinpal callback still resolves it (with test); strict build + jest pass.

### [P2-6] pishbin — delete legacy Prisma stack + README/compose mismatch
- Dead weight alongside real FastAPI backend: `frontend/prisma/`, `frontend/lib/prisma.ts`, `frontend/app/api/prisma-mock/`, `frontend/lib/mock-data.ts`, `docs/PRISMA_SETUP.md`, prisma deps/scripts, `npx prisma generate` in Dockerfile. No page imports any of it.
- README says compose runs "backend and Postgres only" but `docker-compose.yml` defines a frontend service too. `docs/OPENCLAW_GATEWAY_TOKEN.md` is AI-tool noise. `backend/schema.sql` is an empty stub.
- Done when: `grep -ri prisma frontend/ docs/` returns 0 and `npm run build` succeeds; README matches compose services.

### [P2-7] Junk-eviction sweep (multiple repos)
The same `uploads/Obsidian-RECIPE.md` artifact is committed in vamgar, catalogueyar, sudban, negotia (and variants elsewhere). `outputs/` build artifacts are committed in vafa-copilot (560KB pitch-deck PDF), negotia (9.5KB zip), sakhtban (`outputs/sakhtban-onepager.md`).
- Action per repo: `git rm -r` the dir, add `uploads/` + `outputs/` to `.gitignore`, relocate anything worth keeping (e.g. decks → GitHub Releases).
- Done when: `git ls-files | grep -E 'uploads/|outputs/'` is empty per repo.

### [P2-8] Missing LICENSE files
Repos with no LICENSE (several publicly implying/claiming MIT in READMEs):
- **pishbin** — README section claims MIT, no file (public). Highest priority of this group.
- **TabibYar** — badge says `license-TBD`.
- **Didebaan** — public, no license, settings say Proprietary.
- vafa-copilot, nabz, vamgar, sudban, sakhtban, bartakht, Hamgam (public!), mizan-legal-copilot, Granovo, moodist, Nabze-Shahr, motiva, rakhsha, DesignDecide, Banna, Matyab, mand, tippet, peimaneh, cargo-IQ, CMI_Detection.
- Action: add MIT or Apache-2.0 (owner picks per repo; default Apache-2.0 to match catalogueyar/kijoon/sabzina), link from README, align any contradictory claims (shemronkebab README-vs-LICENSE, Didebaan settings).
- Note: negotia LICENSE is an intentional proprietary "All Rights Reserved" — add `"license": "UNLICENSED"` to package.json files instead of changing it.
- Done when: each repo's GitHub metadata reports a license (or UNLICENSED intent is machine-readable).

### [P2-9] Missing/broken READMEs
- **Granovo, Nabze-Shahr, hoshyar** — no README at all (404). Write one from the landing/docs content.
- **Vasiq** — README is a 69-byte stub; expand to describe the Provider Verification & Eligibility Engine.
- **catalogueyar, kijoon, sabab, Qeymatban, peimaneh, cargo-IQ** — GitHub descriptions are empty; add a one-line description (`gh repo edit --description`).
- Done when: every repo has a README ≥1KB and a description.

### [P2-10] negotia — misc fixes
- Add root `.env.example` (`LLM_PROVIDER=mock`, commented `OPENAI_API_KEY=`).
- Fix `web/lib/store.js` policy path: `path.join(process.cwd(), '..', 'config', ...)` breaks outside `web/` cwd — use `import.meta.url`-relative resolution like `web/next.config.mjs` already does.
- Done when: every env var in `src/` is documented; `npm run build && npm start` serves a conversation page from any cwd.

### [P2-11] TabibYar + others — small doc/deps fixes
- TabibYar: `stt-service/server.py` header references `docs/build.md` which doesn't exist — create it or repoint to `stt-service/README.md`; pin `>=` ranges in `stt-service/requirements.txt`.
- Didebaan: `GITHUB_SETUP.md` leaks local path `/Users/massoudshemirani/...` — remove.
- vafa-copilot: `landing/index.html` and `docs/index.html` are byte-identical duplicates — keep the `docs/` copy (serves GitHub Pages).
- Done when: no doc references a nonexistent file; deps resolve deterministically.

---

## P3 — Features & polish

### [P3-1] sudban — validation layer + baseline migration
- Extract scattered manual checks (`if (!price || price <= 0)` in `src/routes/pricing.ts` etc.) into zod schemas per route with uniform Persian 400 errors. Commit a baseline Prisma migration (`prisma migrate diff --from-empty --script`) so `migrate deploy` works non-interactively.
- Done when: manual checks replaced, invalid-body tests return structured 400s; `migrate diff --from-migrations ... --to-schema-datamodel` reports no drift.

### [P3-2] nabz + vafa-copilot — API polish
- nabz: make test fixtures clock-explicit (inject `today` into `compute_signals`/`decide`) instead of the `FIXTURE_ANCHOR` date-shifting hack.
- vafa-copilot: `mvp/api/main.py` uses `sys.path.append` hack and returns `__dict__` — add Pydantic response models for a real OpenAPI schema.
- Done when: tests pass without date-shifting helpers; `/docs` shows typed schemas.

### [P3-3] Hamgam — Next 15 upgrade + Basalam contract tests
- `next@^14.2.35` has CVEs only fixed in 15/16 (documented in frontend README). Upgrade + keep 9 vitest tests green. Add contract tests for `backend/src/connectors/basalam.ts` from documented paths (happy path, auth-error, rate-limit retry).
- Done when: next ≥15, typecheck+test+build pass; connector tests cover the three cases.

### [P3-4] shemronkebab — dependency upgrades
- next 14.2.5 → 14.2.35 minimum (or 15.x), remove `sqlite3` leftover.
- Done when: build/lint/test pass on new pins.

### [P3-5] sabzina — styling regression guard
- CI step: after build, assert the largest CSS chunk contains `.flex` and `bg-sabzina-50` and exceeds a size floor. This failure class (green build, dead CSS) is invisible to unit tests.
- Done when: check fails against a reverted globals.css and passes on main.

### [P3-6] mizan-legal-copilot — polish
- Replace `mailto:hello@mizan.ai` placeholder on landing; surface LLM fallback mode (real vs keyword) in `/analyze` response or logs metric; document the 12,000-char truncation.
- Done when: no placeholder contact; ops can distinguish fallback mode.

### [P3-7] Docs-only repos — implement MVPs
rakhsha, mand, Banna, DesignDecide, tippet, Granovo, motiva (landing-only), hoshyar (outputs-only, no README) are README/ROADMAP/landing-only. For each: follow its own ROADMAP.md to build the smallest runnable MVP (the vafa-copilot pattern — small engine + API + tests — is the house style that works).
- Done when: each repo has runnable code + tests + CI.

### [P3-8] Forks — upstream sync review
worldmonitor, DevOps_Certification, RA3G-Agent, CortexKG are forks with local changes. Check `gh api repos/massoudsh/NAME/compare/upstream` for divergence; either PR useful changes upstream or document the delta in the README.
- Done when: each fork's README states its delta vs upstream.

---

## Execution notes for the CLI AI

1. **Order**: P0 → P1 → P2 → P3. Within P0, Findash secret removal (P0-1) is first.
2. **Clone per repo, branch per task** (`feat/ci`, `chore/junk-eviction`…), conventional commits, PR per task.
3. **Never** rewrite git history on main without explicit owner approval (flagged in P0-1, P1-15, P2-4).
4. **Destructive/ambiguous choices to surface, not decide**: license pick per repo (P2-8), bartakht submodule intent (P2-2), shed57 history rewrite (P2-4), Hamgam public-vs-private (P1-13 preamble).
5. **Verify done-when checks** before declaring a task complete; run tests locally, push, confirm CI status via `gh run watch`.
6. Cross-repo repeat pattern worth automating: "add CI + LICENSE + gitignore `uploads/`/`outputs/` + remove `Obsidian-RECIPE.md`" applies to nearly every repo in this account.
