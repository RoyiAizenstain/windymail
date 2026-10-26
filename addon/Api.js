/**
 * Backend client. Sends the opened message to /api/v1/analyze and validates the
 * response before anything is rendered: the backend is an external service, so
 * its output is untrusted too (threat model T8).
 *
 * Never logs email content; only HTTP status codes and error kinds.
 */

var VERDICTS = ['safe', 'suspicious', 'malicious'];
var MODES = ['organization', 'personal'];

/** Returns a validated result object, or null on any failure. */
function analyzeMessage(message) {
  // Google-signed ID token proving the user's identity to the backend (ADR-011).
  var token = ScriptApp.getIdentityToken();
  if (!token) {
    console.error('WindyMail: no identity token (openid scope missing?)');
    return null;
  }

  var response;
  try {
    response = UrlFetchApp.fetch(BACKEND_BASE_URL + '/api/v1/analyze', {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify(buildAnalyzeRequest(message)),
      muteHttpExceptions: true,
      followRedirects: false,
    });
  } catch (err) {
    console.error('WindyMail: backend unreachable');
    return null;
  }

  var status = response.getResponseCode();
  if (status !== 200) {
    console.error('WindyMail: backend returned HTTP ' + status);
    return null;
  }

  try {
    return parseAnalyzeResponse(JSON.parse(response.getContentText()));
  } catch (err) {
    console.error('WindyMail: invalid backend response');
    return null;
  }
}

/**
 * Builds the request from the opened message. Attachments are sent as metadata
 * only; their contents never leave Gmail.
 */
function buildAnalyzeRequest(message) {
  var request = {
    message_id: message.getId(),
    from: clip(message.getFrom(), LIMITS.from),
    reply_to: clip(message.getReplyTo(), LIMITS.replyTo) || null,
    subject: clip(message.getSubject(), LIMITS.subject),
    auth_results: clip(message.getHeader('Authentication-Results'), LIMITS.authResults) || null,
    body_text: '',
    body_html: null,
    attachments: message
      .getAttachments({ includeInlineImages: false })
      .slice(0, LIMITS.attachments)
      .map(function (a) {
        return {
          filename: clip(a.getName(), LIMITS.filename),
          mime_type: clip(a.getContentType(), LIMITS.mimeType),
          size_bytes: a.getSize(),
        };
      }),
    truncated: false,
  };

  var text = String(message.getPlainBody() || '');
  var html = String(message.getBody() || '');
  request.body_text = clip(text, LIMITS.bodyText);
  request.body_html = clip(html, LIMITS.bodyHtml) || null;
  request.truncated = text.length > LIMITS.bodyText || html.length > LIMITS.bodyHtml;
  return fitToBudget(request);
}

/**
 * Trims body_html, then body_text, until the serialized request fits the byte
 * budget. Each removed character frees at least one byte, so cutting the excess
 * from a field always brings the request under budget in one pass per field.
 */
function fitToBudget(request) {
  ['body_html', 'body_text'].forEach(function (field) {
    var excess = utf8Length(JSON.stringify(request)) - MAX_REQUEST_BYTES;
    if (excess <= 0) return;
    var value = request[field] || '';
    var kept = value.slice(0, Math.max(0, value.length - excess));
    // Never end on half a surrogate pair: JSON escapes a lone half as 6 bytes.
    if (/[\ud800-\udbff]$/.test(kept)) kept = kept.slice(0, -1);
    request[field] = field === 'body_html' ? kept || null : kept;
    request.truncated = true;
  });
  return request;
}

/** UTF-8 byte length of a string (Utilities.newBlob is not available in tests). */
function utf8Length(text) {
  var bytes = 0;
  for (var i = 0; i < text.length; i++) {
    var code = text.charCodeAt(i);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff) {
      bytes += 4;
      i++;
    } else bytes += 3;
  }
  return bytes;
}

/** Keeps only known fields with the expected types; throws on anything else. */
function parseAnalyzeResponse(raw) {
  if (!raw || typeof raw !== 'object') throw new Error('not an object');

  var score = raw.score;
  if (typeof score !== 'number' || score % 1 !== 0 || score < 0 || score > 100) {
    throw new Error('bad score');
  }
  if (VERDICTS.indexOf(raw.verdict) === -1) throw new Error('bad verdict');
  if (MODES.indexOf(raw.mode) === -1) throw new Error('bad mode');
  if (typeof raw.summary !== 'string') throw new Error('bad summary');
  if (!Array.isArray(raw.reasons)) throw new Error('bad reasons');

  var reasons = raw.reasons
    .filter(function (r) {
      return r && typeof r.text === 'string';
    })
    .map(function (r) {
      return { text: r.text, severity: r.severity, details: String(r.details || '') };
    });

  return {
    score: score,
    verdict: raw.verdict,
    summary: raw.summary,
    reasons: reasons,
    partial: raw.partial === true,
    mode: raw.mode,
  };
}

function clip(value, max) {
  var text = String(value == null ? '' : value);
  return text.length > max ? text.slice(0, max) : text;
}
