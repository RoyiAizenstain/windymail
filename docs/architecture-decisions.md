# Architecture Decisions

Format: Context, Decision, Consequences. Status is one of: **Accepted**, **Open**.

Related: [Development Layers](development-layers.md) · [User Stories](user-stories.md)

---

## ADR-001: Thin add-on, all logic in the backend
**Status:** Accepted
**Context:** Apps Script has limited runtime, no good secret storage for third-party keys, and code that is harder to test.
**Decision:** The add-on only extracts message data, renders results, and handles user actions. All analysis, scoring, secrets, and external calls live in the FastAPI backend.
**Consequences:** One source of truth, testable logic, no secrets on the client. Every scan requires a network round-trip.

## ADR-002: UI built only with CardService
**Status:** Accepted
**Context:** Email content and LLM output are attacker-influenced and will be displayed to the user.
**Decision:** Render exclusively with native CardService widgets. LLM text is shown as plain text only, never as HTML or clickable links.
**Consequences:** No XSS surface in the Gmail UI. Limited visual flexibility.

## ADR-003: The LLM is a bounded signal, not the judge
**Status:** Accepted (exact weights Open, see ADR-010)
**Context:** The email body is attacker-controlled and can attempt prompt injection. LLM output is also non-deterministic.
**Decision:** Deterministic signals form the base of the score. The LLM contributes a capped amount and writes the plain-language narrative.
**Consequences:** A manipulated LLM cannot zero out a malicious email. Scores are reproducible and explainable.

## ADR-004: Prompt injection defenses
**Status:** Accepted
**Context:** Same as ADR-003.
**Decision:** Delimit email content and declare it untrusted data; require strict JSON schema output validated with Pydantic; truncate and strip HTML before sending; report AI-directed instructions as a suspicious finding.
**Consequences:** Injection attempts become detection signals. Some legitimate long emails are analyzed only partially.

## ADR-005: Graceful degradation without the LLM
**Status:** Accepted
**Context:** External LLM calls can time out, fail, or return invalid output.
**Decision:** On any LLM failure, return the deterministic-only result marked "partial analysis".
**Consequences:** The add-on always returns a verdict. Partial results lack social-engineering analysis.

## ADR-006: Stable hosted backend instead of ngrok
**Status:** Accepted (host: Render, see ADR-012)
**Context:** The solution must be demonstrated live; tunnel URLs change and connections drop.
**Decision:** Deploy the backend to a stable HTTPS host from Layer 1.
**Consequences:** Reliable demo and fixed add-on configuration. Requires deployment setup early.

## ADR-007: Single scan, no LLM pre-triage
**Status:** Accepted (revised by ADR-013)
**Context:** The original plan had three scan depths plus an LLM triage pass. Triage adds a model call before the real scan, slowing the path it was meant to speed up.
**Decision:** One scan on open (deterministic + LLM). Deep Scan with external reputation checks is future work.
**Consequences:** Simplest UX and code, easiest to explain. No slower, deeper checks in this version.

## ADR-008: Manual reporting to a mock, configurable SOC webhook
**Status:** Accepted (revised by ADR-013)
**Context:** No real Upwind SOC endpoint exists.
**Decision:** The Report button sends to a webhook URL from environment (`SOC_WEBHOOK_URL`), pointing to a mock receiver. Reports carry score, reason IDs, and message identifier, not the email body. Automatic escalation (proposed threshold: score >= 85, above the Red boundary to limit false-positive alerts) is future work.
**Consequences:** Less data exposure. Escalation depends on the user pressing Report.

## ADR-009: Herd Immunity as a privacy-preserving proof of concept
**Status:** Accepted as stretch goal (ADR-013). Built only if time allows.
**Context:** Campaign detection is valuable, but a single-user in-memory demo cannot show it, and naive sender+subject hashes are trivially evaded.
**Decision:** Persist normalized fingerprints in SQLite: `sha256(sender_domain + normalized_subject + sorted_link_domains)`. Store hashes only, never content or recipients. Entries expire after a configurable window.
**Consequences:** Demoable with a second account, no stored email content. Still evadable by attackers who vary content; single-tenant only. Documented as a limitation.

## ADR-011: Backend security design
**Status:** Accepted
**Context:** The backend is reachable from the internet, receives attacker-controlled email content, and spends LLM budget per request. Security awareness is an explicit evaluation criterion.
**Decision:**
* **Authentication:** the add-on obtains a Google-signed ID token (`ScriptApp.getIdentityToken()`, requires the `openid` scope) and sends it as a Bearer token on every request, including `/report`. The backend verifies signature, issuer, expiry, and that the audience matches the add-on's OAuth client ID (`GOOGLE_CLIENT_ID` env var). Any failure → 401.
* **User identity:** the token's `sub` claim is the user ID. It is never stored or logged in clear; where needed (rate limiting, Herd Immunity) it is stored as `sha256(sub + server_salt)`.
* **Rate limiting:** in-memory, per user ID, fixed window (default 20 requests per minute, configurable). Exceeded → 429. Single-instance only, documented as a limitation.
* **Request validation:** strict Pydantic schema, unknown fields rejected; max request size (default 200 KB); body truncated by the add-on before sending.
* **Timeouts:** every outbound call (LLM, webhook) has an explicit timeout.
* **Masking before LLM:** regex masking of email addresses, phone numbers, and long digit sequences (card- or account-like). Documented as best-effort, not full PII protection.
* **Logging:** log request ID, hashed user ID, score, latency, and errors only. Never bodies, subjects, tokens, or LLM prompts.
* **Secrets:** environment variables only; `.env.example` committed; `.env` gitignored; repo scanned for secrets before publishing.
**Consequences:** No shared secret to leak; every request is tied to a verified user. Requires correct OAuth client configuration in the Apps Script project, to be verified early in Layer 1. Rate limiting does not survive restarts or scale across instances.

## ADR-012: Hosting on Render free tier with keep-warm
**Status:** Accepted
**Context:** The backend must be reachable over stable HTTPS from Layer 1 (ADR-006) and answer within the card response window (US-01, about 3 seconds). Render's free tier spins an idle service down after about 15 minutes; the next request waits through a cold start that can exceed Gmail's add-on timeout. The paid plan avoids this at a small cost; we chose not to pay. Cloud Run was the alternative; it needs more setup and still costs money to stay always on.
**Decision:** Deploy the FastAPI backend as a Render web service on the free tier. One instance. Add an unauthenticated `GET /health` endpoint and ping it every 10 minutes from a free external monitor to keep the service warm; warm it manually a few minutes before the demo. Secrets (`ANTHROPIC_API_KEY`, `GOOGLE_CLIENT_ID`, `SOC_WEBHOOK_URL`, hashing salt) set as Render environment variables, never in the repo. Auto-deploy from the public repo's main branch.
**Consequences:** Fixed HTTPS URL, zero cost, minimal setup. Residual cold-start risk if the monitor misses pings; mitigated by the pre-demo warm-up and the fallback recording (Layer 7). In-memory state (rate limiter, ADR-011) resets on every spin-down or redeploy. The free tier has no persistent disk, so SQLite for Herd Immunity (ADR-009) resets too; documented as a limitation. `/health` returns only a fixed status, no version or config. Demo items (demo email set, script, fallback recording) are tasks tracked in Layer 7.

## ADR-013: Scope cut to fit the deadline
**Status:** Accepted
**Context:** About a day and a half of work before submission (Wednesday 28.10, 11:00). The assignment values clear thinking and clean execution over feature completeness.
**Decision:** Build the core: deterministic signals, bounded LLM, basic backend security, simple scoring, clear UI, manual report. Herd Immunity is a stretch goal. Deep Scan, URL reputation, and automatic escalation are documented as future work.
**Consequences:** A smaller product that is secure, explainable, and demo-stable. Fewer "wow" features; the README must explain what was cut and why.

## ADR-014: Branding as WindyMail with a light weather theme
**Status:** Accepted
**Context:** A named product with a consistent voice is more memorable in the demo, and a weather theme ties naturally to Upwind. But security UX must stay unambiguous: a metaphor must never hide what the user should do.
**Decision:** The add-on is called **WindyMail**. Weather wording is used only for headline labels and small touches; every verdict is always followed by a plain-language explanation and a clear action.

| Element | Weather label | Always followed by |
|---------|---------------|--------------------|
| Green (0-29) | ☀️ Clear skies | "This email looks safe." |
| Yellow (30-69) | 🌥️ Storm watch | "Some signs are suspicious. Don't click links or reply until you're sure." |
| Red (70-100) | ⛈️ Storm warning | "This email is very likely malicious. Don't click, reply, or download." |
| Partial analysis (ADR-005) | 🌫️ Limited visibility | "Some checks couldn't run. Verdict based on technical signals only." |
| Report button | 🚩 Report this storm | Confirmation: "Thanks, the security team has been notified." |
| Herd Immunity (stretch) | 🌪️ Storm front | "N people in your organization received a similar message in the last 15 minutes." |

**Rules:** weather words never replace the reasons list; no weather wording inside reasons or technical details; README and code use standard security terms.
**Consequences:** A distinct, friendly product identity. Slight risk of reading as playful on a serious warning, mitigated by the plain-language line under every label.

## ADR-015: Built for non-technical users, in organizations and at home
**Status:** Accepted
**Context:** The target user is not a security expert. WindyMail must work both for an employee in an organization and for a private Gmail user.
**Decision:**
* Main view uses plain language only; technical details stay collapsed (US-10).
* Verdict is never conveyed by color alone: always label + icon + text (accessibility).
* Mode is determined by configuration: if `SOC_WEBHOOK_URL` is set, organization mode (Report button, Herd Immunity if built); otherwise personal mode (guidance to use Gmail's "Report phishing" instead).
**Consequences:** One product for both audiences. Organization-only features degrade gracefully instead of breaking.

## ADR-016: Languages and tech stack
**Status:** Accepted (LLM provider pending confirmation)
**Context:** About a day and a half to build. The stack must be familiar, fast to develop, easy to test, and fit the Gmail add-on platform.
**Decision:**

| Area | Choice | Why |
|------|--------|-----|
| Add-on | Google Apps Script (JavaScript, V8 runtime) + CardService | Required platform for Gmail add-ons; CardService per ADR-002 |
| Add-on tooling | `clasp` | Keeps add-on code in the Git repo, deploy from the command line |
| Backend language | Python 3.12 | Strong ecosystem for parsing email, URLs, and LLM SDKs |
| Backend framework | FastAPI + Uvicorn | Fast to build, async, automatic request validation |
| Validation | Pydantic v2 | Strict request schemas and LLM output validation (ADR-004) |
| Token verification | `google-auth` | Official library for verifying Google ID tokens (ADR-011) |
| HTML parsing | BeautifulSoup | HTML to text, link extraction, hidden text detection |
| Domain parsing | `tldextract` | Correct registered-domain extraction for lookalike checks |
| HTTP client | `httpx` | Explicit timeouts on outbound calls |
| LLM | Anthropic API, fast small model (Claude Haiku) | Low latency for the card response window; structured output |
| Storage | None for core; SQLite only if Herd Immunity is built | Nothing to persist in the core flow |
| Tests | `pytest` | Unit tests per signal, security tests |
| Code quality | `ruff` (lint + format), type hints throughout | Minimal setup, readable code |
| Hosting | Render web service, free tier + keep-warm ping (ADR-012) | Stable HTTPS, zero cost, minimal setup |
| UI language | English | Matches the assignment and reviewers |

**Repo layout:**
```
/addon      Apps Script code, appsscript.json, .clasp.json
/backend    FastAPI app, signals/, llm/, scoring/, tests/
/docs       Planning and decision documents
README.md
```
**Consequences:** Two languages to maintain (JavaScript and Python), kept separate by the thin-add-on design (ADR-001). Dependencies pinned in `requirements.txt`.

## ADR-017: Only normalized technical values are echoed in reasons
**Status:** Accepted
**Context:** The response must not reflect attacker-controlled text (T2, T6), but a reason is only useful when it names the concrete finding ("the link says paypal.com but goes to bit.ly"), and US-10 needs link destinations and authentication results.
**Decision:** `reasons[].details` may include values the backend has parsed and normalized itself: domains, IP addresses, file extensions, and SPF/DKIM/DMARC results. Each is restricted to a narrow character set (for domains, lowercase IDNA form, `[a-z0-9.-]`) and length-capped. Subjects, body text, display names, full URLs, and filenames are never echoed. `reasons[].text` stays fixed wording from the backend, with counts only.
**Consequences:** Reasons are concrete and verifiable without becoming a channel for attacker text. The add-on still escapes everything it renders. The no-echo test keeps covering subjects and body text.

## ADR-018: DMARC failure severity follows the domain's policy
**Status:** Accepted
**Context:** In the live test (27.10) a genuine Israeli newsletter was marked Suspicious only because Gmail recorded `dmarc=fail`. Many small senders fail DMARC because their mailing service isn't set up for their domain; with policy `p=none` the domain owner asks receivers not to act on that, and Gmail delivers the email normally. Treating every failure as high risk teaches users to ignore the warning.
**Decision:** `dmarc=fail` stays high when the policy is `quarantine` or `reject`, or when it is missing or unclear. It is medium ("couldn't confirm the sender, common for newsletters") only when both `p` and `sp` are `none`. The policy is read only from the comment Gmail writes right after `dmarc=fail` in its own `mx.google.com` entry; other comments carry sender-controlled text (addresses), so a planted `p=none` there is ignored.
**Consequences:** Newsletters with a weak DMARC setup score Safe with a visible medium reason instead of Suspicious. An attacker spoofing a `p=none` domain gets medium on the sender check, so the verdict then rests on the link, lookalike, display-name and attachment checks; recorded under Known Limitations.

---

## Open Decisions

## ADR-010: Scoring model
**Status:** Open
**Question:** How to combine deterministic signals and the capped LLM signal into one explainable 0-100 score. Constraint from ADR-003 applies.
**Provisional (Layer 2, accepted 26.10):** points per deterministic finding by severity (high 35, medium 15, low 5), summed and clamped to 0-100, mapped through the verdict thresholds. Expected to become the deterministic half of the final model; the LLM contribution and its cap are still open.
