# Development Layers

Build order and progress tracker. Each layer ends in a working, demoable state; the next layer starts only after that.
This file says **what** to build and **when**. The **why** and the exact rules live in the ADRs; this file only references them.

**Deadline: Wednesday 28.10.2026, 11:00.** Scope was cut to fit (ADR-013).

Status values: `Not started` · `In progress` · `Done` · `Blocked`

Related: [User Stories](user-stories.md) · [Architecture Decisions](architecture-decisions.md) · [Architecture](architecture.md) · [Threat Model](threat-model.md)

---

## Schedule

| When | Layers |
|------|--------|
| Monday 26.10 | 1, 2 |
| Tuesday 27.10 | 3, 4, 5, 6 |
| Tuesday night / Wednesday morning | 7, then Stretch if time allows |
| Wednesday 28.10, 11:00 | Submit |

README is written along the way: each layer adds its section.

---

## Layer 1: End-to-End Skeleton
**Status:** In progress (Steps 1-2 done, Step 3 next)
**Stories:** US-01, US-12 · **ADRs:** 001, 002, 006, 012

- [ ] Apps Script add-on with contextual trigger on message open
- [ ] Card shows sender, subject, placeholder score
- [x] FastAPI `/api/v1/analyze` returning mock JSON in the final response schema ([architecture.md](architecture.md))
- [ ] Backend deployed to Render free tier (ADR-012)
- [ ] `GET /health` endpoint (unauthenticated, fixed response) + external keep-warm ping every 10 minutes
- [ ] Minimal OAuth scopes in `appsscript.json` (including `openid`)
- [ ] Verify early that `ScriptApp.getIdentityToken()` returns a token the backend can validate (ADR-011)
- [x] Config loaded from environment, `.env.example` committed
- [x] Public repo created; README skeleton

**Done when:** opening any email shows the mock result from the deployed backend.

### Layer 1 step-by-step plan
One step at a time; each step ends with its own check before the next starts. **You** marks actions only the account owner can do.

**Step 1: Repo setup**
- [x] `git init`; folders `/addon`, `/backend`, `/docs` (ADR-016)
- [x] `.gitignore`: `.env`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `.clasprc.json`; `docs/assignment.md` kept local (the brief is not published)
- [x] README skeleton: one-paragraph pitch, status, section headings to fill per layer
- [x] Public GitHub repo created and pushed: https://github.com/RoyiAizenstain/windymail
- Check: repo visible on GitHub, no secrets in it.

**Step 2: Backend skeleton (local)**
- [x] `backend/app/main.py`: FastAPI app, `GET /health` → `{"status": "ok"}`, `POST /api/v1/analyze` → fixed mock in the final response schema; `/docs` and `/openapi.json` off unless `ENABLE_API_DOCS=true`
- [x] `backend/app/models.py`: Pydantic v2 request and response models per [architecture.md](architecture.md), `extra="forbid"`, length bounds on all strings and lists; `mode` field added to the response (ADR-015)
- [x] `backend/app/config.py`: settings read from environment only; fail fast on invalid values
- [x] `backend/app/verdict.py`: score → verdict thresholds (0-29 / 30-69 / 70-100)
- [x] `backend/.env.example` with every variable name, no values; `requirements.txt` and `requirements-dev.txt` pinned; `pyproject.toml` with `ruff` config (incl. bandit `S` rules)
- [x] Tests (22): `/health` ok; `/analyze` valid request, schema-valid response, no echo of request content; 422 on unknown, missing, overlong, and negative fields; organization vs personal mode; docs disabled by default; verdict boundaries
- Check: `uvicorn` runs locally, `pytest` and `ruff check` pass.

**Step 3: Deploy to Render**
- [ ] `render.yaml` (root dir `backend`, Python 3.12 pinned, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, free plan)
- [ ] **You:** create a free Render account, connect the GitHub repo, create the service from `render.yaml`, set env vars in the Render dashboard
- Check: `https://<service>.onrender.com/health` returns ok over HTTPS.

**Step 4: Keep-warm ping**
- [ ] **You:** free UptimeRobot (or cron-job.org) monitor on `/health`, interval 10 minutes or less
- Check: monitor shows the service up; after 20+ idle minutes `/health` still answers fast.

**Step 5: Add-on skeleton (no backend yet)**
- [ ] **You:** enable the Apps Script API at script.google.com/home/usersettings; `npm i -g @google/clasp`; `clasp login`
- [ ] `clasp create --type standalone --rootDir addon`; commit `.clasp.json` (script ID only, not a secret)
- [ ] `addon/appsscript.json`: V8 runtime; `addOns.common` (name WindyMail, logo, homepage trigger); `addOns.gmail.contextualTriggers` on message open; scopes: `gmail.addons.execute`, `gmail.addons.current.message.readonly`, `script.external_request`, `openid`; `urlFetchWhitelist` limited to the Render URL
- [ ] `addon/Code.js`: homepage card; message-open card showing sender, subject, placeholder score, built with CardService only (ADR-002)
- [ ] `clasp push`; **You:** Deploy → Test deployments → Install in your Gmail account
- Check: opening an email in Gmail shows the WindyMail card with the right sender and subject.
- Note: `current.message.readonly` is requested now rather than a metadata-only scope because Layer 2 needs the body; this avoids a second consent prompt a day later.

**Step 6: Connect add-on to backend**
- [ ] Backend URL stored in Script Properties (config, not hard-coded)
- [ ] `UrlFetchApp` POST of the request schema with an explicit error path (`muteHttpExceptions`): any failure shows a plain-language "couldn't check this email" card, never a raw error
- [ ] Card renders the mock score and verdict returned by Render
- Check: opening an email shows the mock result from the deployed backend.

**Step 7: Identity token verification (ADR-011)**
- [ ] Add-on sends `Authorization: Bearer <ScriptApp.getIdentityToken()>` on every call
- [ ] Find the audience safely: decode the token payload inside Apps Script and log **only** the `aud` claim, never the token; set it as `GOOGLE_CLIENT_ID` on Render
- [ ] Backend dependency verifies signature, issuer, expiry and audience with `google-auth`; any failure → 401; applied to `/analyze` now and `/report` when it exists
- [ ] Tests: missing token → 401, invalid token → 401 (verification mocked)
- Check: the card still works from Gmail; `curl` without a token gets 401.
- Note: verification is pulled forward from Layer 4 so the deployed backend is never open. Layer 4 adds rate limiting, size limits and the remaining tests.

**Step 8: Close the layer**
- [ ] README: what WindyMail is, architecture overview, how to run locally and deploy
- [ ] Tick the boxes above, set Layer 1 status to Done

---

## Layer 2: Deterministic Signal Engine
**Status:** Not started
**Stories:** US-02, US-03, US-10

- [ ] Add-on extracts headers, body (text + HTML), attachment metadata
- [ ] Sender authentication results (SPF, DKIM, DMARC) from `Authentication-Results`
- [ ] Display name vs address mismatch; Reply-To vs From mismatch
- [ ] Lookalike domains
- [ ] Link text vs destination mismatch; IP links; URL shorteners
- [ ] Risky attachment extensions
- [ ] Hidden text in HTML
- [ ] Plain-language reason for every finding
- [ ] Unit test per signal
- [ ] README: signals section

**Done when:** a phishing test email shows concrete, correct reasons.

---

## Layer 3: LLM Integration
**Status:** Not started
**Stories:** US-04, US-09 · **ADRs:** 003, 004, 005

- [ ] Psychological vector analysis
- [ ] Injection defenses per ADR-004
- [ ] Fallback per ADR-005
- [ ] Injection and LLM-failure tests
- [ ] README: LLM safety section

**Done when:** the prompt-injection test email does not lower the score.

---

## Layer 4: Backend Security (basic)
**Status:** Not started
**Stories:** US-11 · **ADRs:** 011

- [ ] Google ID token verification on `/analyze` and `/report` (built in Layer 1, Step 7; confirm `/report` is covered)
- [ ] Hashed user ID; per-user rate limiting
- [ ] Payload size limits and strict schema
- [ ] Timeouts on outbound calls
- [ ] Masking before LLM call
- [ ] Logging hygiene
- [ ] Tests: missing/invalid token → 401, oversized → 413, rate limit → 429
- [ ] README: security section and threat model

**Done when:** unauthenticated and oversized requests are rejected; tests pass.

---

## Layer 5: Scoring Model (simple)
**Status:** Blocked on ADR-010
**Stories:** US-02 · **ADRs:** 003, 010

- [ ] Weighted sum of signals, capped LLM contribution, clamp to 0-100
- [ ] README: scoring section

---

## Layer 6: UX & Report
**Status:** Not started
**Stories:** US-01, US-06, US-10 · **ADRs:** 002, 008

- [ ] Traffic light verdict with WindyMail weather labels and plain-language summary (ADR-014)
- [ ] Collapsible technical details
- [ ] Report to Security Team button (mock webhook) in organization mode; "Report phishing" guidance in personal mode (ADR-015, US-13)
- [ ] Screenshots for README

---

## Layer 7: Demo & Final README
**Status:** Not started

- [ ] Demo email set prepared in the demo account
- [ ] Demo script
- [ ] Fallback recording
- [ ] Pre-demo warm-up step in the demo script (call `/health`, run one scan)
- [ ] README: trade-offs, limitations, future work; final review
- [ ] Repo check: no secrets committed

---

## Stretch: Herd Immunity
**Status:** Optional — only if Layer 7 is done
**Stories:** US-07 · **ADRs:** 009

- [ ] Fingerprint store with hashed user IDs and expiry
- [ ] Banner in the card
- [ ] Demo with a second account

---

## Future Work (documented in README, not built)
* Deep Scan with URL reputation lookups (US-05)
* Automatic SOC escalation (US-08)
* Attachment content analysis
