# CLAUDE.md - WindyMail: Gmail Add-on Malicious Email Scorer

**Product name: WindyMail.** Light weather theme in UI labels only, always followed by a plain-language explanation (ADR-014).

Home assignment for **Upwind Security** (Security Analyst role): a Gmail Add-on that analyzes an opened email and shows a maliciousness score with a clear, explainable verdict, backed by a FastAPI service.

**Guiding principle:** the role is security-focused. Every decision must be defensible from a security perspective first, and from a product perspective second. Prefer a smaller feature set that is secure, explainable, and demo-stable.

## Documents
* [docs/assignment.md](docs/assignment.md) — the original Upwind assignment. **Source of truth for requirements.** Local only: gitignored, never published.
* [docs/architecture.md](docs/architecture.md) — component diagram, request flow, API contract.
* [docs/development-layers.md](docs/development-layers.md) — build order, layer by layer, with done criteria.
* [docs/user-stories.md](docs/user-stories.md) — what each persona needs and acceptance criteria.
* [docs/architecture-decisions.md](docs/architecture-decisions.md) — decisions taken (ADRs) and open decisions. **Single source of truth for rules and thresholds.**
* [docs/threat-model.md](docs/threat-model.md) — assets, attackers, threats and mitigations, out-of-scope.
* [docs/demo-script.md](docs/demo-script.md) — the live demo: warm-up, the four demo emails in the inbox, flow, failure handling, likely questions.
* **Card images:** the "WindyMail Assets" Claude Design canvas (https://claude.ai/artifact/PZjXCz3BxP5QcmJyL2LLYB) holds the wordmark and the three verdict banners (Sora); exported as 2x PNGs into `backend/static/`.

When starting a session, check the status lines in `development-layers.md` to see where work stopped. When finishing a task, tick its box and update the layer status.

## Tech stack (ADR-016)
* **Add-on:** Google Apps Script (JavaScript) + CardService, managed with `clasp`
* **Backend:** Python 3.12, FastAPI, Pydantic v2, `google-auth`, BeautifulSoup, `tldextract`, `httpx`
* **LLM:** Anthropic API via the official `anthropic` SDK (2.3.0, pinned), Claude Haiku `claude-haiku-5-5`, model name a setting (`LLM_MODEL`)
* **Tests & quality:** `pytest`, `ruff`, type hints
* **Repo:** `/addon`, `/backend`, `/docs`, `README.md`

## Target users
Non-technical users, both **employees in an organization** and **private Gmail users** (ADR-015). Plain language first; never rely on color alone; organization-only features hidden in personal mode.

## Core rules for working on this repo
* Email content, attachments, and all external responses (LLM, APIs) are untrusted input.
* The LLM never decides the score alone (ADR-003): its findings add at most +20 and never subtract.
* The LLM returns labels only; the card never shows text the model wrote, only fixed wording per label (ADR-019). It is one bounded call, not an agent: the model never chooses or calls tools.
* UI only through CardService; every untrusted string escaped as plain text (ADR-002).
* Reasons use fixed wording from `backend/app/signals/messages.py`; only normalized technical values (domains, IPs, extensions, auth results) are echoed (ADR-017).
* Never fetch or resolve a URL from an email (SSRF); links are parsed only.
* Attachment bytes never leave Gmail: the add-on sends only structural facts (real type, a zip's table of contents, PDF actions), never decompresses, and stays within fixed budgets; anything unread is "not inspected", never clean (ADR-021).
* The card shows plain-language reasons and the total only, never parsed values or per-reason points: they would turn WindyMail into an attacker's test lab (threat T12, ADR-017).
* Secrets only from environment variables; never log email bodies, prompts, LLM answers or tokens.
* Each layer must end in a working demo before starting the next.

## Working on the code
* **Backend tests:** `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .` (Windows venv; the system Python has no pytest). Tests never call the real LLM: `conftest.py` clears the LLM settings.
* **Add-on checks:** `node addon/test/logic.test.js` from the repo root.
* **Deploy:** `git push` to `main` → Render redeploys the backend. `clasp push` from the repo root → updates the add-on. When both change: backend first, wait until Render shows it live, then `clasp push` (the backend rejects request fields it doesn't know). When a card image in `backend/static/` changes, bump `ASSET_VERSION` in `addon/Config.js`, and `clasp push` only after Render serves the new image: Gmail caches each image by its URL, so an early push caches the old one under the new version.
* **Kill switches on Render, no deploy:** `LLM_ENABLED=false` (rules only, `partial`), `ATTACHMENT_INSPECTION=false` (attachment facts ignored), unset `SOC_WEBHOOK_URL` (personal mode).
* **Live check:** Render logs carry one line per request (`app.access: request id=… method=… path=… status=… latency_ms=… user=<hash>`) and one per LLM call (`llm: outcome=ok|skipped:no_key|timeout|status:… model=… latency_ms=…`), one per report (`report: outcome=ok|timeout|status:… user=<hash> latency_ms=…`).

## Verdict thresholds
* 🟢 0-29 Safe (☀️ Clear skies) · 🟡 30-69 Suspicious (🌥️ Storm watch) · 🔴 70-100 Malicious (⛈️ Storm warning)
* Escalation is manual only (Report button, ADR-008)

## Deadline
**Wednesday 28.10.2026, 11:00.** Scope cut per ADR-013. Herd Immunity is the only stretch goal.

## Open items
* **Status (27.10):** Layers 1-8 done, live and checked in Gmail.
  * 1-5: skeleton, rule engine, bounded LLM, backend security (`app/security.py`), scoring.
  * 6: Report button (`/api/v1/report`, mock SOC on webhook.site).
  * 6.5 UI: wordmark and verdict banners, colored severity labels, AI findings as purple tags, Report in a fixed footer; no Technical details on the card (T12; analyst view designed as ADR-020).
  * 7: README with six screenshots, demo script, secrets check; no fallback recording (the screenshots are the fallback).
  * 8: attachment inspection (ADR-021); live test email "[WindyMail test] Attachments: Q4 report and form" (macro .docx + JavaScript PDF, 65).
* **Known gap, future work:** only the opened message is scanned, not the whole conversation (threat T14); plan in the README's future work and the tracker's Future Work list.
* **Open, all optional:** personal mode live, the injection email without its injected line (Layer 3), a 429 from Gmail (Layer 4). Herd Immunity (stretch) not started.
* **Scoring (ADR-010, accepted):** high 35 / medium 15 / low 5 per reason, LLM +20 cap; decisive findings set a minimum of 70: `invoice.pdf.exe`, right-to-left file names, hidden AI instructions, a file whose real type contradicts its trusted name. Any scoring change must keep `pytest tests/test_corpus.py` green (18 realistic emails with expected verdicts).
* **Hosting:** Render free tier with an UptimeRobot keep-warm ping (ADR-012).
