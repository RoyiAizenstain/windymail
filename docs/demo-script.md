# WindyMail demo script

About 7 minutes, then questions. Live in Gmail, with the README screenshots as the fallback.

## Before the demo

**The demo set** is already in the demo inbox (checked live 27.10). Scores can move by a few points between runs, because the AI check can add or drop a finding; the verdicts don't change.

| # | Expected | Email in the inbox | Why it scores that way |
|---|---|---|---|
| 1 | ☀️ Safe (20) | "Quick one": "Are you at your desk? I need a small favour before the board meeting." | No request yet, so no rule fires beyond a minor one; the AI still tags the pressure. |
| 2 | 🌥️ Suspicious (50) | "[WindyMail demo] Quick favour": buy gift cards, send the codes | Pressure plus a request for money (high), confirmed by the AI. No link, no attachment. |
| 3 | ⛈️ Malicious (100) | "[WindyMail test] Phishing: your account is limited" | Link text shows paypal.com but goes elsewhere, links to bare IP addresses, hidden links, an `.html` attachment, pressure. |
| 4 | ⛈️ Malicious (70) | "Payment needed": buy gift cards, plus a visible "AI assistant: …" instruction | The instruction aimed at AI tools counts against the email, on top of the gift-card pressure. |

**10 minutes before**
1. Wake the backend: open `https://windymail-backend.onrender.com/health` and wait for `{"status":"ok"}` (the free tier sleeps after about 15 idle minutes).
2. Open email 1 once, so the first live scan is warm.
3. Open the webhook.site tab for the demo `SOC_WEBHOOK_URL`, cleared, in a second window.
4. Have the README open in a tab: its six screenshots are the fallback.

## The demo

**1. The problem (30 s).** Phishing is aimed at people who aren't security experts. WindyMail sits next to the email and answers one question in plain language: is this safe, and why?

**2. Safe, but watched (45 s).** Open email 1.
- The banner: a word and a shape, never color alone; the score bar and number.
- The 🤖 AI check tags pressure ("Rushes you to act") that no phrase rule matched.
- Say: the AI notices, but it can only add up to 20 points, so one vague message stays Safe. That is the opening of a CEO scam; the next email is where it goes.

**3. Suspicious: CEO gift-card scam (1 min).** Open email 2.
- No link, no attachment, so a link scanner sees nothing.
- The rules catch urgency plus a request for money; the 🤖 AI check confirms the tactics by meaning.
- Say: the AI adds at most 20 points and never subtracts. A fooled model can fail to add points, but it can't make a malicious email look safe.

**4. Malicious (1.5 min).** Open email 3.
- Read two or three reasons: the link that shows paypal.com but goes elsewhere, the bare IP address, the HTML attachment.
- Say: links are parsed, never opened, so the backend can't be tricked into calling an attacker's server.

**5. Prompt injection (1 min).** Open email 4.
- The email tells "AI assistant" tools what to conclude.
- It scores higher, not lower: the rules catch instructions aimed at AI before the model runs, and count them as evidence against the email. Hidden from the reader, they would be decisive on their own (minimum 70).
- Say: the model only returns labels from a fixed list, and the card never shows its words, so an injected sentence has nowhere to go.

**6. Report (1 min).** On email 3 or 4, press **Report to Security Team**.
- "✅ Report sent" on the card.
- Switch to webhook.site: the report arrives with the message ID, score, verdict and reason IDs. Point out what is not there: no subject, no sender, no body, and the reporter is a hash.

**7. Close (30 s).** Security first: the email, the AI and even our own backend's answers are treated as untrusted. Every limit and trade-off is written down in the README and the threat model.

## If something goes wrong

| Problem | What to do |
|---|---|
| "WindyMail couldn't check this email" | The backend was asleep. Press **Try again** after about 30 seconds; meanwhile, explain the fail-safe card. |
| Banner image missing | The verdict word is still in the score line; carry on. |
| AI check shows "Limited visibility" | The LLM timed out or is off. The rules' verdict still arrives: show it as the fallback working. |
| Report fails | Webhook URL expired or changed: show the 502 handling ("never a false 'sent'") and move on. |
| Gmail itself won't load | Walk through the README screenshots: all three verdicts, prompt injection, the report confirmation. |

## Likely questions

- **Why not let the AI decide?** It reads the attacker's text. Rules decide most of the score; the AI is a bounded, add-only signal (ADR-003, ADR-019).
- **Why not an agent?** An agent would let the email steer what the system does (open links, call tools): SSRF and data leaks. One bounded call, labels only.
- **Couldn't an attacker use WindyMail to test their emails?** Yes, that's threat T12. The card hides the parsed values and the weights, and the rate limit slows probing; the score itself still leaks. An analyst-only details view is designed (ADR-020).
- **What leaves the user's mailbox?** To the backend: the open message, capped and validated. To Anthropic: subject and plain body, masked. To the security team: IDs and the score only.
- **What would you do next?** Automatic alerts for near-certain threats, domain age and reputation from our own code, shared state for more than one instance.
