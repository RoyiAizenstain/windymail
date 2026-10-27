# User Stories

Personas:
* **Employee** — a regular, non-technical email user inside an organization.
* **Personal user** — a private Gmail user with no organization and no security team behind them.
* **Security Analyst** — a SOC team member who receives reports and alerts.
* **Admin** — deploys and operates the add-on and backend.

Acceptance criteria double as the basis for tests.

**Status at submission (27.10):** ✅ Done · 🔄 Changed (built differently, reason given) · 🔮 Future work · ⭐ Stretch, not built.

Related: [Development Layers](development-layers.md) · [Architecture Decisions](architecture-decisions.md) · [Threat Model](threat-model.md)

---

## Employee

**US-01: See a verdict when I open an email** · ✅ Done
As an employee, I want to see a clear risk verdict when I open an email, so I know immediately whether it is safe.
* Score 0-100 with Green / Yellow / Red verdict (Safe / Suspicious / Malicious banner: word, shape and color).
* Result appears in about 3 seconds or less (2-3 s when the backend is warm; a cold start on the free tier can take longer, ADR-012).
* No security jargon in the main view.

**US-02: Understand why** · ✅ Done
As an employee, I want to see the reasons behind the verdict, so I can trust it and learn to spot threats myself.
* Each reason is one short plain-language sentence.
* Each reason maps to a concrete finding in the email.

**US-03: Be warned about fake senders and links** · ✅ Done
As an employee, I want to be told when a sender or link is not what it pretends to be, so I don't fall for impersonation.
* Flags name/address mismatch, lookalike domains, and links whose real destination differs from the text.

**US-04: Be warned about manipulation** · ✅ Done
As an employee, I want to know when an email is pressuring me (urgency, authority, money or password requests), so I can slow down before acting.
* Detected manipulation types are shown with a short explanation.

**US-05: Get a deeper check when unsure** · 🔮 Future work (single scan, ADR-007)
As an employee, I want to run a deeper scan on a suspicious email, so I can get more certainty before acting.
* Deep Scan button always available; suggested automatically on Yellow.

**US-06: Report an email in one click** · ✅ Done
As an employee, I want to report a suspicious email to the security team in one click, so reporting takes no effort.
* Confirmation shown after reporting.

**US-07: Know if colleagues got the same email** · ⭐ Stretch, not built (ADR-009)
As an employee, I want to know if others in my organization received a similar message, so I understand it may be a targeted campaign.
* Banner with count and time window.
* No identities of other recipients are revealed.

---

## Personal User

**US-13: Use WindyMail without an organization** · ✅ Done (covered by tests; not checked live)
As a personal user, I want the same clear verdict and reasons, and to know what to do next, even though I have no security team.
* Same verdict, reasons, and plain-language action line as an employee.
* Report button is replaced by guidance: use Gmail's "Report phishing", and don't click or reply.
* No organization-only features shown (no SOC report, no Herd Immunity banner).

---

## Security Analyst

**US-08: Receive alerts on critical threats** · 🔮 Future work
As a security analyst, I want automatic alerts for high-confidence malicious emails, so I can respond without waiting for user reports.
* Alert includes score, reasons, and message identifiers, not the full body.
* Threshold per ADR-008.

**US-09: Trust that the scorer cannot be fooled by the email itself** · ✅ Done
As a security analyst, I want the analysis to resist instructions hidden inside emails, so attackers cannot make malicious emails look safe.
* Injection attempts are detected and reported as a finding.
* Email content cannot lower the deterministic part of the score.

**US-10: See technical details** · 🔄 Changed
As a security analyst, I want access to the raw technical findings, so I can investigate further.
* ~~Collapsible details section with authentication results, link destinations, and signal list.~~
* **Changed (27.10):** not shown on the card, so the add-on is a weaker test lab for attackers (threat T12, ADR-017). The backend still returns the details; analysts get the reason IDs in each report. A details view for analysts only is designed as future work (ADR-020).

---

## Admin

**US-11: Run a backend that is safe to expose** · ✅ Done
As an admin, I want the backend to accept only authenticated requests and protect secrets and email data, so it cannot be abused or leak information.
* Unauthenticated, oversized, or malformed requests are rejected.
* Secrets only in environment variables.
* Email bodies and tokens never logged.

**US-12: Configure integrations without code changes** · 🔄 Changed
As an admin, I want the SOC webhook, thresholds, and API keys to be configurable, so I can adapt the deployment.
* ~~All configured through environment variables.~~
* **Changed (27.10):** integrations and operations are environment variables: `SOC_WEBHOOK_URL`, `ANTHROPIC_API_KEY`, `LLM_ENABLED`, `LLM_MODEL`, `RATE_LIMIT_PER_MINUTE`, `GOOGLE_CLIENT_ID`. Verdict thresholds (30 / 70) and scoring weights stay in code on purpose: a changed environment variable could quietly weaken detection, while a code change must pass the 18-email test set and review (ADR-010).
