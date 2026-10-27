/**
 * Backend client. Sends the opened message to /api/v1/analyze and validates the
 * response before anything is rendered: the backend is an external service, so
 * its output is untrusted too (threat model T8).
 *
 * Never logs email content; only HTTP status codes and error kinds.
 */

var VERDICTS = ['safe', 'suspicious', 'malicious'];
var MODES = ['organization', 'personal'];
var SEVERITIES = ['high', 'medium', 'low'];
var TACTICS = ['urgency', 'authority', 'credentials', 'financial', 'impersonation'];
var REASON_ID = /^[a-z0-9_]{1,64}$/;

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
  var files = message.getAttachments({ includeInlineImages: false }).slice(0, LIMITS.attachments);
  var inspections = inspectAll(files);
  var request = {
    message_id: message.getId(),
    from: clip(message.getFrom(), LIMITS.from),
    reply_to: clip(message.getReplyTo(), LIMITS.replyTo) || null,
    subject: clip(message.getSubject(), LIMITS.subject),
    auth_results: clip(message.getHeader('Authentication-Results'), LIMITS.authResults) || null,
    body_text: '',
    body_html: null,
    attachments: files.map(function (a, i) {
      return {
        filename: clip(a.getName(), LIMITS.filename),
        mime_type: clip(a.getContentType(), LIMITS.mimeType),
        size_bytes: a.getSize(),
        inspection: inspections[i],
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
 * Structural facts per attachment (ADR-021), within fixed budgets. The bytes stay
 * here; only the facts are sent. Anything over budget or unreadable is marked
 * "not inspected", which the backend reports, never treats as clean.
 */
function inspectAll(files) {
  var started = Date.now();
  var budget = { entries: INSPECT.maxEntries };
  return files.map(function (file, i) {
    if (i >= INSPECT.maxFiles || Date.now() - started > INSPECT.timeBudgetMs) {
      return { inspected: false };
    }
    try {
      if (file.getSize() > INSPECT.maxBytes) return { inspected: false };
      return inspectBytes(file.getBytes(), budget);
    } catch (err) {
      return { inspected: false };
    }
  });
}

function inspectBytes(bytes, budget) {
  var facts = {
    inspected: true,
    kind: fileKind(bytes),
    encrypted: false,
    entries: [],
    macros: false,
    pdf_actions: [],
  };
  if (facts.kind === 'zip') {
    var dir = readZipDirectory(bytes, budget);
    if (!dir) return { inspected: false };
    facts.encrypted = dir.encrypted;
    facts.entries = dir.entries;
    facts.macros = dir.macros;
  } else if (facts.kind === 'pdf') {
    facts.pdf_actions = pdfActions(bytes);
  }
  return facts;
}

/** The real type from the first bytes ("magic number"), whatever the name says. */
function fileKind(bytes) {
  if (startsWith(bytes, [0x4d, 0x5a]) || startsWith(bytes, [0x7f, 0x45, 0x4c, 0x46])) return 'exe';
  if (startsWith(bytes, [0x50, 0x4b, 0x03, 0x04]) || startsWith(bytes, [0x50, 0x4b, 0x05, 0x06])) {
    return 'zip';
  }
  if (startsWith(bytes, [0xd0, 0xcf, 0x11, 0xe0])) return 'ole';
  var head = latin1(bytes, 0, 1024);
  // PDF readers accept the marker after some junk, so look a little further in.
  if (head.indexOf('%PDF-') !== -1) return 'pdf';
  var start = head.replace(/^\xef\xbb\xbf/, '').replace(/^\s+/, '').toLowerCase();
  if (start.charAt(0) === '<' && /<(html|!doctype html|script|svg|body|iframe|form)\b/.test(start)) {
    return 'html';
  }
  return 'unknown';
}

/**
 * Reads a zip's table of contents (the central directory at its end): entry names,
 * the encrypted flag, and whether an Office macro project is inside. Nothing is
 * unpacked, so a zip bomb has nothing to explode. Returns null if there is no
 * readable table of contents.
 */
function readZipDirectory(bytes, budget) {
  var n = bytes.length;
  var end = -1;
  for (var p = n - 22; p >= Math.max(0, n - 22 - 65535); p--) {
    if (startsWithAt(bytes, p, [0x50, 0x4b, 0x05, 0x06])) {
      end = p;
      break;
    }
  }
  if (end < 0) return null;
  var total = u16(bytes, end + 10);
  var pos = u32(bytes, end + 16);
  var dir = { encrypted: false, entries: [], macros: false };
  for (var i = 0; i < Math.min(total, 1000); i++) {
    if (pos + 46 > n || !startsWithAt(bytes, pos, [0x50, 0x4b, 0x01, 0x02])) break;
    var nameLength = u16(bytes, pos + 28);
    if (pos + 46 + nameLength > n) break;
    var name = latin1(bytes, pos + 46, pos + 46 + nameLength);
    if (u16(bytes, pos + 8) & 1) dir.encrypted = true;
    if (/(^|\/)vbaproject\.bin$/i.test(name)) dir.macros = true;
    if (name.slice(-1) !== '/' && budget.entries > 0) {
      dir.entries.push(name.slice(0, INSPECT.maxEntryChars));
      budget.entries--;
    }
    pos += 46 + nameLength + u16(bytes, pos + 30) + u16(bytes, pos + 32);
  }
  return dir;
}

/** PDF actions that run something when the file opens, from the first megabyte. */
function pdfActions(bytes) {
  var text = latin1(bytes, 0, INSPECT.pdfScanBytes);
  var found = [];
  if (/\/JavaScript|\/JS\b/.test(text)) found.push('javascript');
  if (text.indexOf('/OpenAction') !== -1) found.push('open_action');
  if (text.indexOf('/Launch') !== -1) found.push('launch');
  if (text.indexOf('/EmbeddedFile') !== -1) found.push('embedded_file');
  return found;
}

function startsWith(bytes, signature) {
  return startsWithAt(bytes, 0, signature);
}

function startsWithAt(bytes, pos, signature) {
  if (pos < 0 || pos + signature.length > bytes.length) return false;
  for (var i = 0; i < signature.length; i++) {
    if ((bytes[pos + i] & 0xff) !== signature[i]) return false;
  }
  return true;
}

function u16(bytes, pos) {
  return (bytes[pos] & 0xff) | ((bytes[pos + 1] & 0xff) << 8);
}

function u32(bytes, pos) {
  return u16(bytes, pos) + u16(bytes, pos + 2) * 65536;
}

/** Bytes as one character each (Apps Script bytes are signed), in chunks. */
function latin1(bytes, start, end) {
  var out = '';
  var stop = Math.min(end, bytes.length);
  for (var i = start; i < stop; i += 8192) {
    var chunk = [];
    for (var j = i; j < Math.min(i + 8192, stop); j++) chunk.push(bytes[j] & 0xff);
    out += String.fromCharCode.apply(null, chunk);
  }
  return out;
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

/**
 * Reports the message to the security team via /api/v1/report (ADR-008).
 * Identifiers and the score only, never content. Returns true once the backend
 * confirms the report was delivered.
 */
function reportMessage(messageId, score, reasonIds) {
  var token = ScriptApp.getIdentityToken();
  if (!token) {
    console.error('WindyMail: no identity token (openid scope missing?)');
    return false;
  }

  var response;
  try {
    response = UrlFetchApp.fetch(BACKEND_BASE_URL + '/api/v1/report', {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + token },
      payload: JSON.stringify(buildReportRequest(messageId, score, reasonIds)),
      muteHttpExceptions: true,
      followRedirects: false,
    });
  } catch (err) {
    console.error('WindyMail: backend unreachable (report)');
    return false;
  }

  var status = response.getResponseCode();
  if (status !== 200) {
    console.error('WindyMail: report returned HTTP ' + status);
    return false;
  }
  try {
    return JSON.parse(response.getContentText()).status === 'received';
  } catch (err) {
    console.error('WindyMail: invalid report response');
    return false;
  }
}

function buildReportRequest(messageId, score, reasonIds) {
  return {
    message_id: String(messageId),
    score: score,
    reason_ids: reasonIds.filter(function (id, i) {
      return REASON_ID.test(id) && reasonIds.indexOf(id) === i;
    }),
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
      return {
        // Sent back in a report; only catalog-shaped IDs are kept (the backend checks them again).
        id: typeof r.id === 'string' && REASON_ID.test(r.id) ? r.id : null,
        text: r.text,
        severity: SEVERITIES.indexOf(r.severity) === -1 ? null : r.severity,
        fromAi: r.source === 'ai',
        // `details` and `points` are not kept: the card doesn't show the parsed values
        // or the scoring weights, so testing drafts against it reveals less (oracle risk).
      };
    });

  // Labels only (ADR-019). Unknown values are dropped; an older backend without
  // the field simply means no AI section.
  var ai = raw.ai && typeof raw.ai === 'object' ? raw.ai : {};
  var tactics = Array.isArray(ai.tactics) ? ai.tactics : [];

  return {
    score: score,
    verdict: raw.verdict,
    summary: raw.summary,
    reasons: reasons,
    ai: {
      ran: ai.ran === true,
      tactics: tactics.filter(function (tactic, i) {
        return TACTICS.indexOf(tactic) !== -1 && tactics.indexOf(tactic) === i;
      }),
      injection: ai.injection === true,
    },
    partial: raw.partial === true,
    mode: raw.mode,
  };
}

function clip(value, max) {
  var text = String(value == null ? '' : value);
  return text.length > max ? text.slice(0, max) : text;
}
