# Architecture & API Contract

Related: [Architecture Decisions](architecture-decisions.md) · [Threat Model](threat-model.md)

---

## 1. Component Diagram

```
+------------------------------------------------------------------+
|                      GMAIL (user's browser)                      |
|  Gmail Add-on (Google Apps Script)                               |
|  * Contextual trigger on message open                            |
|  * Extracts headers, body, attachment metadata                   |
|  * Renders result with CardService only (ADR-002)                |
|  * No secrets, no scoring logic (ADR-001)                        |
+--------------------------------+---------------------------------+
                                 | HTTPS POST (JSON) + auth header
                                 v
+------------------------------------------------------------------+
|                FASTAPI BACKEND (Render, ADR-006/012)             |
|                                                                  |
|  [1] Auth & rate limit           Google ID token (ADR-011)       |
|  [2] Request validation          size limits, strict schema      |
|  [3] Normalizer                  links as a browser reads them,  |
|                                  redirects unwrapped, HTML text  |
|  [4] Signal engine (rules)       sender, lookalikes, links,      |
|                                  attachments, hidden content,    |
|                                  language EN/HE (ADR-017, 018)   |
|  [5] LLM analyzer (Haiku)        labels only, schema-validated   |
|                                  twice (ADR-003, 004, 005, 019)  |
|  [6] Scorer                      [4] + [5] capped at +20         |
|                                  (ADR-010)                       |
|  [7] Herd immunity tracker       stretch goal (ADR-009)          |
|  [8] SOC notifier                manual reports, mock (ADR-008)  |
+------------------+-----------------------------+-----------------+
                   |                             |
                   v                             v
          +----------------+            +-----------------+
          | LLM provider   |            | Mock SOC        |
          | (untrusted     |            | webhook         |
          |  response)     |            |                 |
          +----------------+            +-----------------+
```

## 2. Request Flow
1. User opens an email; the add-on trigger fires.
2. Add-on builds the request (Section 3) and calls `/api/v1/analyze`.
3. Backend runs steps [1] to [6] (and [7] if the stretch goal is built). The rules [4] and the LLM [5] look at the email independently; the LLM receives only the masked subject and plain body, and returns labels. If the LLM gives no answer, the rules' result is returned marked `partial` (ADR-005).
4. Backend returns the response (Section 3); the add-on validates it and renders it, wording the AI labels itself (ADR-019).
5. User may press **Report**, which calls `/api/v1/report`.

---

## 3. API Contract

All requests carry a Google ID token as a Bearer header (ADR-011, Section 4). All fields are treated as untrusted.

### `POST /api/v1/analyze`

Request:
```json
{
  "message_id": "string",
  "from": "string",
  "reply_to": "string | null",
  "subject": "string",
  "auth_results": "string | null",
  "body_text": "string",
  "body_html": "string | null",
  "attachments": [
    { "filename": "string", "mime_type": "string", "size_bytes": 0,
      "inspection": { "inspected": true, "kind": "exe | zip | pdf | ole | html | unknown",
                      "encrypted": false, "entries": ["string"], "macros": false,
                      "pdf_actions": ["javascript | open_action | launch | embedded_file"] } }
  ],
  "truncated": false
}
```

`inspection` (optional, ADR-021): facts the add-on read from the file, never its bytes. `inspected: false` means it wasn't looked inside (over budget or unreadable). `entries` are names from a zip's table of contents, at most 50 per request and 255 characters each; never echoed, logged or sent to the LLM.

Limits (ADR-011): body truncated by the add-on before sending (HTML first, then plain text, to fit 190 KB; `truncated: true` when anything was cut); backend rejects requests over 200 KB (413, checked before the body is read), unknown fields and over-long fields (422). Over the per-user rate limit (default 20 per minute) the answer is 429 with `Retry-After`. Error responses never echo the submitted values (ADR-011).

Response:
```json
{
  "score": 0,
  "verdict": "safe | suspicious | malicious",
  "summary": "One plain-language sentence.",
  "reasons": [
    {
      "id": "reply_to_mismatch",
      "category": "sender | link | attachment | content | manipulation",
      "severity": "low | medium | high",
      "text": "Replies will go to a different address than the sender.",
      "details": "Technical detail for analysts.",
      "source": "rules | ai",
      "points": 35
    }
  ],
  "manipulation": ["urgency", "authority", "credentials", "financial", "impersonation"],
  "ai": { "ran": true, "tactics": ["authority"], "injection": false },
  "herd": { "count": 0, "window_minutes": 15 },
  "partial": false,
  "mode": "organization | personal"
}
```

* `partial: true` when the LLM step gave no answer: failure, no key, or switched off (ADR-005).
* `ai` says whether the AI check ran and what it found, as labels only; the add-on words them itself and never shows text written by the model (ADR-019). `reasons[].source` is `ai` for reasons only the AI check found. `reasons[].points` is what each reason added to the score; they add up to `score`, except when a decisive finding lifts it to 70, which `summary` then says (ADR-010). `manipulation` combines the rules' and the AI's tactics.
* `herd` is `null` unless the Herd Immunity stretch goal is built and the mode is organization.
* `mode` tells the add-on which actions to show: Report button in organization mode, "Report phishing" guidance in personal mode (ADR-015). Derived from whether `SOC_WEBHOOK_URL` is set.
* Request strings and lists have upper bounds; unknown fields are rejected (422). Nothing from the request is echoed in the response, except normalized technical values (domains, IPs, file extensions, auth results) in `reasons[].details` (ADR-017).
* `reasons[].details` feeds the collapsible analyst section (US-10).

### `POST /api/v1/report`

Request:
```json
{ "message_id": "string", "score": 0, "reason_ids": ["string"] }
```
Response: `{ "status": "received" }`

* `message_id` is Gmail's ID (letters, digits, `-`, `_`); `score` a whole number 0-100 (strict); `reason_ids` at most 50, each one an ID from the reason catalog, else 422.
* Organization mode only: in personal mode the endpoint answers 404. Same token check and per-user rate limit as `/analyze`.
* The backend posts to `SOC_WEBHOOK_URL` (https only, 5 s timeout, no redirects): `event`, `source`, `reported_at`, `reporter` (salted user hash), `message_id`, `score`, `verdict` (derived from the score by the backend), `reason_ids`. A webhook failure, timeout or non-2xx answer → 502, so the add-on never shows a false confirmation.
* No email body, subject or sender is sent in reports (ADR-008). The score is the user's claim, copied from the `/analyze` result by the add-on.

### `GET /static/{name}`
Unauthenticated: the card's images (`wordmark.png`, `safe.png`, `suspicious.png`, `malicious.png`), fetched by Gmail. A fixed list: any other name is 404, so no request can read another file. Fixed files designed for the add-on, never content from an email.

### `GET /health`
Unauthenticated keep-warm endpoint (ADR-012). Response: `{ "status": "ok" }`. Returns no version, config, or other data.

---

## 4. Authentication
Every endpoint except `/health` (`/analyze` and `/report`) requires `Authorization: Bearer <Google ID token>`, verified per ADR-011. The verified user ID is used only in hashed form (rate limiting, Herd Immunity distinct-user count).
