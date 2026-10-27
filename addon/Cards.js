/**
 * Card builders. CardService only (ADR-002). Every untrusted string (email fields,
 * backend and LLM text) goes through toPlainText() before display.
 *
 * Verdict wording per ADR-014: weather label, plain-language verdict word, and an
 * action line, so the verdict never relies on color or metaphor alone (ADR-015).
 */

var VERDICT_UI = {
  safe: {
    label: '☀️ Clear skies',
    word: 'Safe',
    action: 'This email looks safe.',
  },
  suspicious: {
    label: '🌥️ Storm watch',
    word: 'Suspicious',
    action: "Some signs are suspicious. Don't click links or reply until you're sure.",
  },
  malicious: {
    label: '⛈️ Storm warning',
    word: 'Malicious',
    action: "This email is very likely malicious. Don't click, reply, or download.",
  },
};

/** Severity in words, so it never relies on color (ADR-015). */
var SEVERITY_WORDS = { high: 'High risk', medium: 'Worth checking', low: 'Minor' };

/**
 * Fixed wording for each label the AI check returns (ADR-019). The model's own text
 * is never shown: it has just read the attacker's email and could be steered.
 */
var AI_TACTIC_WORDS = {
  urgency: 'Rushes you to act',
  authority: 'Claims to come from someone in charge',
  credentials: 'Asks for a password, code or sign-in',
  financial: 'Asks for money or payment details',
  impersonation: "Pretends to come from a company, bank or person it isn't",
};
var AI_INJECTION_WORDS = 'Tries to give instructions to automated checks';

var PARTIAL_LINE = "🌫️ Limited visibility: some checks couldn't run. Verdict based on technical signals only.";

/** Personal mode has no security team: Gmail's own report is the next step (US-13). */
var PERSONAL_REPORT_LINES = [
  "Don't click links, open attachments, or reply.",
  'To report it, open the <b>⋮</b> menu at the top right of the email and choose ' +
    '<b>Report phishing</b>. This helps Gmail protect you and others.',
];

function buildHomepageCard() {
  var section = CardService.newCardSection().addWidget(
    CardService.newTextParagraph().setText('Open an email to check whether it is safe.')
  );
  return newCard('Email check').addSection(section).build();
}

function buildResultCard(message, result) {
  var ui = VERDICT_UI[result.verdict];

  var verdict = CardService.newCardSection()
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel(ui.label)
        .setText('<b>' + ui.word + '</b> · risk score ' + result.score + '/100')
        .setWrapText(true)
    )
    .addWidget(CardService.newTextParagraph().setText(toPlainText(ui.action)));
  if (result.partial) {
    verdict.addWidget(CardService.newTextParagraph().setText(toPlainText(PARTIAL_LINE)));
  }
  if (result.summary) {
    verdict.addWidget(CardService.newTextParagraph().setText(toPlainText(result.summary)));
  }

  var reasons = CardService.newCardSection().setHeader('Why');
  if (result.reasons.length === 0) {
    reasons.addWidget(CardService.newTextParagraph().setText('No warning signs found.'));
  }
  result.reasons.forEach(function (reason) {
    reasons.addWidget(CardService.newTextParagraph().setText(reasonLine(reason)));
  });

  var aiSection = buildAiSection(result.ai);

  var email = CardService.newCardSection()
    .setHeader('Email')
    .addWidget(decorated('From', message.getFrom()))
    .addWidget(decorated('Subject', message.getSubject() || '(no subject)'));

  var card = newCard('Email check').addSection(verdict).addSection(reasons);
  if (aiSection) card.addSection(aiSection);
  card.addSection(buildReportSection(message, result));
  card.addSection(email);
  if (result.reasons.length > 0) card.addSection(buildDetailsSection(result.reasons));
  return card.build();
}

/**
 * "<b>High risk:</b> text", or "<b>Worth checking · AI check:</b> text" for reasons
 * only the AI check found. Labels come from fixed maps, never the backend.
 */
function reasonLine(reason) {
  var word = SEVERITY_WORDS[reason.severity];
  var label = word && reason.fromAi ? word + ' · AI check' : word;
  return (label ? '<b>' + label + ':</b> ' : '• ') + toPlainText(reason.text);
}

/** What the AI check found, in fixed wording; empty when it didn't run. */
function aiLines(ai) {
  if (!ai || !ai.ran) return [];
  var found = ai.tactics
    .filter(function (tactic) {
      return AI_TACTIC_WORDS.hasOwnProperty(tactic);
    })
    .map(function (tactic) {
      return '• ' + AI_TACTIC_WORDS[tactic];
    });
  if (ai.injection) found.push('• ' + AI_INJECTION_WORDS);
  if (found.length === 0) return ['The AI check read this email and found no pressure tactics.'];
  return ['The AI check read this email and found:'].concat(found);
}

/** "🤖 AI check" section, so the user sees the AI took part and what it found. */
function buildAiSection(ai) {
  var lines = aiLines(ai);
  if (lines.length === 0) return null;
  var section = CardService.newCardSection().setHeader('🤖 AI check');
  lines.forEach(function (line) {
    section.addWidget(CardService.newTextParagraph().setText(toPlainText(line)));
  });
  return section;
}

/**
 * Organization mode: one-click report to the security team (US-06, ADR-008).
 * Personal mode: there is no security team, so point to Gmail's own "Report
 * phishing" instead (US-13, ADR-015). Shown for every verdict: the user may
 * spot something the checks missed.
 */
function buildReportSection(message, result) {
  var section = CardService.newCardSection().setHeader('Think this email is a scam?');
  if (result.mode !== 'organization') {
    PERSONAL_REPORT_LINES.forEach(function (line) {
      section.addWidget(CardService.newTextParagraph().setText(line));
    });
    return section;
  }

  var report = CardService.newTextButton()
    .setText('Report to Security Team')
    .setTextButtonStyle(CardService.TextButtonStyle.FILLED)
    .setOnClickAction(
      CardService.newAction()
        .setFunctionName('onReport')
        .setParameters(reportParameters(message.getId(), result))
    );
  return section
    .addWidget(
      CardService.newTextParagraph().setText(
        'Let your security team know. They get the risk score and what WindyMail found, ' +
          'not the content of the email.'
      )
    )
    .addWidget(CardService.newButtonSet().addButton(report));
}

/** Action parameters must be strings; the reason IDs travel as one comma-joined value. */
function reportParameters(messageId, result) {
  return {
    messageId: String(messageId),
    score: String(result.score),
    reasonIds: result.reasons
      .map(function (reason) {
        return reason.id;
      })
      .filter(Boolean)
      .join(','),
  };
}

/** Shown after a report is delivered (US-06: confirmation after reporting). */
function buildReportedCard() {
  var section = CardService.newCardSection()
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel('✅ Report sent')
        .setText('<b>Thanks. Your security team has been told.</b>')
        .setWrapText(true)
    )
    .addWidget(
      CardService.newTextParagraph().setText(
        "Until they get back to you, don't click links, open attachments, or reply to this email."
      )
    );
  return newCard('Reported').addSection(section).build();
}

/** Collapsed analyst view (US-10): what each check found, in technical terms. */
function buildDetailsSection(reasons) {
  var section = CardService.newCardSection()
    .setHeader('Technical details')
    .setCollapsible(true)
    .setNumUncollapsibleWidgets(1)
    .addWidget(CardService.newTextParagraph().setText('For security teams: what each check found.'));
  reasons.forEach(function (reason) {
    if (reason.details) {
      section.addWidget(CardService.newTextParagraph().setText(detailsLine(reason)));
    }
  });
  return section;
}

/** "• (+35) Authentication-Results: dmarc=fail": the points show how the score adds up. */
function detailsLine(reason) {
  var points = reason.points === null || reason.points === undefined ? '' : '(+' + reason.points + ') ';
  return '• ' + points + toPlainText(reason.details);
}

/** Shown when the backend is unreachable, slow, or returns something invalid. */
function buildErrorCard() {
  var retry = CardService.newTextButton()
    .setText('Try again')
    .setOnClickAction(CardService.newAction().setFunctionName('onRetry'));

  var section = CardService.newCardSection()
    .addWidget(
      CardService.newTextParagraph().setText(
        "WindyMail couldn't check this email right now. The service may be starting up; " +
          'try again in a few seconds.'
      )
    )
    .addWidget(
      CardService.newTextParagraph().setText(
        "Until it's checked, be careful with links, attachments, and requests for money or passwords."
      )
    )
    .addWidget(CardService.newButtonSet().addButton(retry));

  return newCard('Check unavailable').addSection(section).build();
}

function newCard(subtitle) {
  return CardService.newCardBuilder().setHeader(
    CardService.newCardHeader().setTitle('WindyMail').setSubtitle(subtitle)
  );
}

/** A label/value row for an untrusted value. */
function decorated(label, value) {
  return CardService.newDecoratedText()
    .setTopLabel(label)
    .setText(toPlainText(value))
    .setWrapText(true);
}

/**
 * CardService text widgets interpret basic HTML (<a>, <b>, <font>). Untrusted text
 * is escaped so it stays inert plain text, and truncated for display (ADR-002).
 */
function toPlainText(value) {
  var text = String(value == null ? '' : value);
  if (text.length > MAX_DISPLAY_CHARS) {
    text = text.slice(0, MAX_DISPLAY_CHARS) + '…';
  }
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
