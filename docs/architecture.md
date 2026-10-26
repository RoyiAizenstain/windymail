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
|  [3] Normalizer                  HTML -> text, extract links,    |
|                                  detect hidden text              |
|  [4] Signal engine               deterministic checks            |
|  [5] LLM analyzer                bounded, schema-validated       |
|                                  (ADR-003, 004, 005)             |
|  [6] Scorer                      combines [4] + [5] (ADR-010)    |
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
3. Backend runs steps [1] to [6] (and [7] if the stretch goal is built).
4. Backend returns the response (Section 4); the add-on renders it.
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
    { "filename": "string", "mime_type": "string", "size_bytes": 0 }
  ]
}
```

Limits (ADR-011): body truncated by the add-on before sending; backend rejects payloads over 200 KB (413) and unknown fields.

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
      "details": "Technical detail for analysts."
    }
  ],
  "manipulation": ["urgency", "authority", "credentials", "financial"],
  "herd": { "count": 0, "window_minutes": 15 },
  "partial": false
}
```

* `partial: true` when the LLM step failed (ADR-005).
* `reasons[].details` feeds the collapsible analyst section (US-10).

### `POST /api/v1/report`

Request:
```json
{ "message_id": "string", "score": 0, "reason_ids": ["string"] }
```
Response: `{ "status": "received" }`

No email body is sent in reports (ADR-008).

### `GET /health`
Unauthenticated keep-warm endpoint (ADR-012). Response: `{ "status": "ok" }`. Returns no version, config, or other data.

---

## 4. Authentication
Every endpoint except `/health` (`/analyze` and `/report`) requires `Authorization: Bearer <Google ID token>`, verified per ADR-011. The verified user ID is used only in hashed form (rate limiting, Herd Immunity distinct-user count).
