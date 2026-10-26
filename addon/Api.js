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
  var response;
  try {
    response = UrlFetchApp.fetch(BACKEND_BASE_URL + '/api/v1/analyze', {
      method: 'post',
      contentType: 'application/json',
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

/** Layer 1 request: headers only. Body and attachments are added in Layer 2. */
function buildAnalyzeRequest(message) {
  return {
    message_id: message.getId(),
    from: clip(message.getFrom(), LIMITS.from),
    reply_to: clip(message.getReplyTo(), LIMITS.replyTo) || null,
    subject: clip(message.getSubject(), LIMITS.subject),
    auth_results: null,
    body_text: '',
    body_html: null,
    attachments: [],
  };
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
