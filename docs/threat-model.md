# Threat Model

**Status:** Complete for the current scope.

Related: [Architecture Decisions](architecture-decisions.md) · [Development Layers](development-layers.md)

---

## 1. Assets (what we protect)
* Email content of the user (body, headers, attachments metadata).
* Secrets: LLM API key, SOC webhook URL, auth configuration.
* Integrity of the verdict (a malicious email must not be shown as safe).
* Backend availability and LLM budget.
* Herd Immunity store.

## 2. Threat Actors
* **Email attacker:** controls the full content of the email being analyzed. The primary adversary.
* **Internet attacker:** can reach the backend URL directly.
* **Curious insider / operator:** has access to logs or the server.

## 3. Entry Points
* Email content passed from the add-on to the backend.
* Backend HTTP API (`/analyze`, `/report`, and unauthenticated `/health`).
* Responses from external services (LLM, URL reputation APIs).

## 4. Threats and Mitigations

| # | Threat | Actor | Mitigation | Reference |
|---|--------|-------|------------|-----------|
| T1 | Prompt injection makes a malicious email look safe | Email attacker | LLM returns labels only, never user-facing text; strict schema checked twice; points capped at +20 and never subtracted; random per-request delimiter; injection phrases caught by rules too (hidden: high, visible: medium) and by the LLM, as a finding against the email | ADR-003, ADR-004, ADR-019 |
| T2 | Malicious content rendered in the UI (XSS, deceptive links) | Email attacker | CardService only, LLM text as plain text | ADR-002 |
| T3 | Evasion of deterministic signals (obfuscated links, hidden text) | Email attacker | Links normalized as a browser reads them (whitespace, backslashes, `user@host`, percent-encoding, punycode, decimal/hex/octal IPs); Google and SafeLinks redirects unwrapped; addresses carried inside any link also checked; auth results trusted only from Gmail's own entry; lookalikes after character normalization; inline hidden-text detection; trimmed bodies and crashed checks reported, never silent; URLs never fetched | Layer 2, ADR-018 |
| T4 | Oversized or malformed payload crashes or slows the backend | Email / Internet attacker | Size limits, strict schema, timeouts | ADR-011 |
| T5 | Unauthenticated use of the backend, LLM budget drain | Internet attacker | Google ID token verification, per-user rate limiting | ADR-011 |
| T6 | Leakage of email content through logs or reports | Insider | No bodies, subjects, or tokens in logs or reports | ADR-008, ADR-011 |
| T7 | Sensitive data sent to the external LLM provider | — | Subject and plain body only (no headers, addresses, links, attachments or user identity); capped at 8,000 characters; links, emails, phone numbers and long numbers masked; logs carry outcome and latency only; `LLM_ENABLED` switch | ADR-011, ADR-019 |
| T8 | Malicious or malformed response from an external service | External service | Validate all external responses before use | ADR-004 |
| T9 | Secret leakage through the repository | — | Environment variables only, `.env` gitignored, pre-publish scan | ADR-011 |
| T10 | Herd Immunity store reveals who received what | Insider | Salted hashes of user IDs only, no content, expiry | ADR-009, ADR-011 |
| T11 | Replay or forged requests to `/report` | Internet attacker | Same token verification as `/analyze` | ADR-011 |

## 5. Out of Scope (explicitly not defended)
* A compromised Google account or compromised Gmail itself.
* Attacks on the LLM provider's infrastructure.
* Sophisticated evasion of Herd Immunity by varying campaign content.
* Full sandboxed analysis of attachment contents.
* Multi-tenant isolation.

## 6. Known Limitations
* Rate limiting is in-memory and single-instance; it resets whenever the free-tier instance spins down or redeploys (ADR-012).
* `/health` is public; it does no work beyond a fixed response and reveals nothing about the service.
* Residual cold-start risk on the free tier if keep-warm pings are missed.
* Masking before the LLM call is best-effort and will miss some sensitive data (names, addresses, numbers written in words). The subject and body of every analyzed email go to Anthropic while the LLM step is on.
* Retention period for the Herd Immunity store to be set if the stretch goal is built.
* Bodies over the request budget are trimmed; padding can push a link past the cut. Reported as a low finding ("too long to check fully"), not a silent gap.
* The domain suffix list is bundled with the backend (no outbound call per request), so very new top-level domains may be parsed less precisely until the dependency is updated.
* Spoofing a domain whose DMARC policy is `p=none` gets only a medium sender reason (ADR-018); the verdict then rests on the link, lookalike, display-name and attachment checks.
* Proofpoint and Mimecast link wrappers are not unwrapped (the target is encoded or held on their servers); addresses carried inside links on unknown sites are checked, but not trusted for the text-vs-destination check (decoy risk).
* Hidden content is detected from inline styles only; content hidden by stylesheets is a blind spot, and newsletters that hide a mobile menu with links get a medium `hidden_link`.
* The LLM step uses the fastest, smallest model (Haiku, ADR-016); it is the least robust against subtle manipulation. The labels-only contract and the cap, not the model, carry the guarantee.
* Rule-based language checks are phrase lists in English and Hebrew; other languages, and wording outside the lists, rely on the LLM alone.
