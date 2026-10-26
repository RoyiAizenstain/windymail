# WindyMail

A Gmail Add-on that analyzes an opened email and shows a maliciousness score (0-100) with a clear, explainable verdict: **Safe**, **Suspicious**, or **Malicious**, plus the concrete reasons behind it.

Built as a home assignment for the Upwind Security Analyst role. The brief: build a Gmail Add-on, backed by a backend service, that analyzes an opened email and presents a maliciousness score with a verdict and the reasoning behind it, treating emails, attachments, and external responses as untrusted input. The scope and signals were left open. The design priority is security first, product second: a smaller feature set that is secure, explainable, and stable in a live demo.

> **Status:** work in progress. Layer 1 (end-to-end skeleton) is complete: the add-on runs in Gmail and gets an authenticated response from the deployed backend, which still returns a mock verdict. Real analysis comes next. Progress: [docs/development-layers.md](docs/development-layers.md).

---

## Contents
1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Signals](#signals)
4. [LLM safety](#llm-safety)
5. [Scoring](#scoring)
6. [Security](#security)
7. [Running locally](#running-locally)
8. [Deployment](#deployment)
9. [Trade-offs, limitations, and future work](#trade-offs-limitations-and-future-work)
10. [Design documents](#design-documents)

---

## What it does
_To be written (Layer 6)._

## Architecture

Two components: a thin Gmail Add-on and a FastAPI backend that holds all logic, scoring, and secrets ([ADR-001](docs/architecture-decisions.md)).

```
Gmail ── user opens an email ──▶ Gmail Add-on (Apps Script, runs on Google's servers)
                                   │ reads only the open message
                                   │ POST /api/v1/analyze  + Google ID token
                                   ▼
                                 FastAPI backend (Render)
                                   │ 1. verify ID token        → 401 if invalid
                                   │ 2. validate strict schema → 422 if malformed
                                   │ 3. analyze → score → verdict
                                   ▼
                                 JSON verdict ──▶ Add-on validates it ──▶ CardService card
```

| Component | Where | Responsibility |
|---|---|---|
| [`addon/`](addon/) | Google Apps Script (V8), deployed with `clasp` | Contextual trigger on message open, builds the request, validates the response, renders cards. No secrets, no scoring. |
| [`backend/`](backend/) | Python 3.12, FastAPI, Pydantic v2, on Render | Authentication, input validation, signal analysis, LLM call, scoring. |

**Design choices worth noting**
* **Least privilege in Gmail.** The add-on requests four scopes: run as a Gmail add-on, read *only the currently open message*, call an external service, and `openid`. It cannot read the inbox, send mail, or touch Drive.
* **Outbound allowlist.** `urlFetchWhitelist` in the manifest restricts the add-on to the backend URL.
* **Every request is authenticated.** The add-on sends a Google-signed ID token; the backend verifies signature, issuer, expiry, and audience (the add-on's OAuth client ID). No shared secret exists to leak.
* **Strict input, bounded size.** Unknown fields are rejected and every string and list has an upper bound.
* **The backend is untrusted too.** The add-on validates the response shape and values before rendering, and escapes every string, because CardService text widgets interpret basic HTML: an email subject like `<a href=…>` would otherwise become a live link.
* **Fail closed.** The backend refuses to start without `GOOGLE_CLIENT_ID`; the add-on shows a plain-language "couldn't check this email" card (with retry) on any failure, never a raw error.

API contract, request flow, and component diagram: [docs/architecture.md](docs/architecture.md).

## Signals
_To be written (Layer 2)._

## LLM safety
_To be written (Layer 3)._

## Scoring
_To be written (Layer 5)._

## Security
_To be written (Layer 4)._

## Running locally

**Backend** (Python 3.12):
```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then fill in GOOGLE_CLIENT_ID
export $(grep -v '^#' .env | xargs)   # or set the variables in your shell
uvicorn app.main:app --reload
```

**Tests and lint:**
```bash
cd backend && pytest && ruff check . && ruff format --check .
node addon/test/logic.test.js     # from the repo root: add-on request/response/escaping logic
```

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_CLIENT_ID` | Yes | Expected `aud` of the add-on's ID token. Find it by running `logTokenAudience()` ([addon/Diagnostics.js](addon/Diagnostics.js)) in the Apps Script editor. |
| `SOC_WEBHOOK_URL` | No | When set, the add-on runs in organization mode (Report button). Empty means personal mode. |
| `ENABLE_API_DOCS` | No | Serve `/docs` and `/openapi.json`. Default `false`. |

## Deployment

**Backend on Render** ([ADR-012](docs/architecture-decisions.md)). Free tier, Frankfurt, auto-deploy on push to `main`; configuration in [`render.yaml`](render.yaml). Set `GOOGLE_CLIENT_ID` in the Render dashboard. The free tier sleeps after ~15 idle minutes, so an UptimeRobot monitor pings the unauthenticated `GET /health` (fixed `{"status":"ok"}`, nothing else) every 5 minutes.

**Add-on with clasp:**
```bash
npm install -g @google/clasp
clasp login                       # the Google account that will use the add-on
clasp push                        # from the repo root; pushes addon/ per .clasp.json
```
Then in the Apps Script editor: **Deploy → Test deployments → Install**, and open any email in Gmail. If you deploy your own backend, update `BACKEND_BASE_URL` in [addon/Config.js](addon/Config.js) and `urlFetchWhitelist` in [addon/appsscript.json](addon/appsscript.json) together.

Google shows an "unverified app" warning for a personal test deployment; that is expected. A real rollout would go through Google's verification or a Workspace admin install.

## Trade-offs, limitations, and future work
_To be written (Layer 7)._

## Design documents
* [Architecture and API contract](docs/architecture.md)
* [Architecture decisions (ADRs)](docs/architecture-decisions.md)
* [Development layers](docs/development-layers.md): build order and progress
* [User stories](docs/user-stories.md)
* [Threat model](docs/threat-model.md)
