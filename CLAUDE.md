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
* **LLM:** Anthropic API, Claude Haiku
* **Tests & quality:** `pytest`, `ruff`, type hints
* **Repo:** `/addon`, `/backend`, `/docs`, `README.md`

## Target users
Non-technical users, both **employees in an organization** and **private Gmail users** (ADR-015). Plain language first; never rely on color alone; organization-only features hidden in personal mode.

## Core rules for working on this repo
* Email content, attachments, and all external responses (LLM, APIs) are untrusted input.
* The LLM never decides the score alone (ADR-003).
* UI only through CardService; LLM text rendered as plain text (ADR-002).
* Secrets only from environment variables; never log email bodies or tokens.
* Each layer must end in a working demo before starting the next.

## Verdict thresholds
* 🟢 0-29 Safe (☀️ Clear skies) · 🟡 30-69 Suspicious (🌥️ Storm watch) · 🔴 70-100 Malicious (⛈️ Storm warning)
* Escalation is manual only (Report button, ADR-008)

## Deadline
**Wednesday 28.10.2026, 11:00.** Scope cut per ADR-013. Herd Immunity is the only stretch goal.

## Open items
Scoring model (ADR-010). Hosting decided: Render free tier with keep-warm ping (ADR-012).
