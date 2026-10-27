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
* The LLM returns labels only; the card never shows text the model wrote, only fixed wording per label (ADR-019).
* UI only through CardService; every untrusted string escaped as plain text (ADR-002).
* Reasons use fixed wording from `backend/app/signals/messages.py`; only normalized technical values (domains, IPs, extensions, auth results) are echoed (ADR-017).
* Never fetch or resolve a URL from an email (SSRF); links are parsed only.
* Secrets only from environment variables; never log email bodies, prompts, LLM answers or tokens.
* Each layer must end in a working demo before starting the next.

## Working on the code
* **Backend tests:** `cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .` (Windows venv; the system Python has no pytest). Tests never call the real LLM: `conftest.py` clears the LLM settings.
* **Add-on checks:** `node addon/test/logic.test.js` from the repo root.
* **Deploy:** `git push` to `main` → Render redeploys the backend. `clasp push` from the repo root → updates the add-on. When both change: backend first, wait until Render shows it live, then `clasp push` (the backend rejects request fields it doesn't know).
* **Live check:** Render logs carry one line per request (`app.access: request id=… method=… path=… status=… latency_ms=… user=<hash>`) and one per LLM call (`llm: outcome=ok|skipped:no_key|timeout|status:… model=… latency_ms=…`).

## Verdict thresholds
* 🟢 0-29 Safe (☀️ Clear skies) · 🟡 30-69 Suspicious (🌥️ Storm watch) · 🔴 70-100 Malicious (⛈️ Storm warning)
* Escalation is manual only (Report button, ADR-008)

## Deadline
**Wednesday 28.10.2026, 11:00.** Scope cut per ADR-013. Herd Immunity is the only stretch goal.

## Open items
* **Status (27.10):** Layers 1-3 done (skeleton, rule engine, bounded LLM); Layer 4 (backend security) next. Live A/B prompt-injection email test from Layer 3 not yet reported.
* **Layer 4 built** in `app/security.py`: 200 KB cap (413), per-user rate limit (429), 422 and 500 responses that never echo input, own access log without client IPs (`app.access`, `X-Request-ID`).
* **Scoring (ADR-010):** provisional model live (high 35 / medium 15 / low 5 per reason, LLM +20 cap); final weights still open.
* Hosting decided: Render free tier with keep-warm ping (ADR-012).
