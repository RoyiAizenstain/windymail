/**
 * Card builders. CardService only (ADR-002). Every untrusted string (email fields,
 * backend and LLM text) goes through toPlainText() before display.
 *
 * Verdict wording per ADR-014: weather label, plain-language verdict word, and an
 * action line, so the verdict never relies on color or metaphor alone (ADR-015).
 * The banner image repeats the verdict; the text below it still carries it, so the
 * card reads the same if an image fails to load.
 */

var VERDICT_UI = {
  safe: {
    label: '☀️ Clear skies',
    word: 'Safe',
    color: '#137333',
    action: 'This email looks safe.',
  },
  suspicious: {
    label: '🌥️ Storm watch',
    word: 'Suspicious',
    color: '#B06000',
    action: "Some signs are suspicious. Don't click links or reply until you're sure.",
  },
  malicious: {
    label: '⛈️ Storm warning',
    word: 'Malicious',
    color: '#C5221F',
    action: "This email is very likely malicious. Don't click, reply, or download.",
  },
};

/** Severity in words and a shape, so it never relies on color (ADR-015). */
var SEVERITY_WORDS = { high: 'High risk', medium: 'Worth checking', low: 'Minor' };
var SEVERITY_MARKS = { high: '▲', medium: '●', low: '○' };
var SEVERITY_COLORS = { high: '#C5221F', medium: '#B06000', low: '#5F6368' };
/** One color for everything the AI check found, so its findings read as a set. */
var AI_COLOR = '#7627BB';

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

/** Organization mode: what the Report button sends (ADR-008). */
var REPORT_NOTE = 'Sends the score and findings, never the email itself.';
var REPORT_BUTTON_COLOR = '#1A73E8';

/** Shown with no email open: what WindyMail does and how to read a result. */
function buildHomepageCard() {
  var intro = CardService.newCardSection().addWidget(
      CardService.newTextParagraph().setText(
        'Open an email and WindyMail checks it for signs of phishing and scams, then tells you why.'
      )
    );
  var legend = CardService.newCardSection().setHeader('How to read the result');
  ['safe', 'suspicious', 'malicious'].forEach(function (verdict) {
    var ui = VERDICT_UI[verdict];
    legend.addWidget(
      CardService.newDecoratedText()
        .setTopLabel(ui.label)
        .setText(verdictWord(ui))
        .setBottomLabel(ui.action)
        .setWrapText(true)
    );
  });
  return CardService.newCardBuilder()
    .addSection(wordmarkSection())
    .addSection(intro)
    .addSection(legend)
    .build();
}

/**
 * The wordmark in its own section, so Gmail draws a line under it. It is the
 * header: CardService can't set a header font, so the brand font (Sora) comes as
 * an image, centered in the image itself.
 */
function wordmarkSection() {
  return CardService.newCardSection().addWidget(cardImage('wordmark', 'WindyMail'));
}

function buildResultCard(message, result) {
  var ui = VERDICT_UI[result.verdict];

  var verdict = CardService.newCardSection()
    .addWidget(cardImage(result.verdict, ui.word + ' (' + ui.label + ')'))
    .addWidget(
      CardService.newDecoratedText().setTopLabel('Risk score').setText(scoreLine(result.score, ui))
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
    var row = CardService.newDecoratedText().setText(toPlainText(reason.text)).setWrapText(true);
    var label = reasonLabel(reason);
    if (label) row.setTopLabel(label);
    reasons.addWidget(row);
  });

  var aiSection = buildAiSection(result.ai);

  var email = CardService.newCardSection()
    .setHeader('Email')
    .setCollapsible(true)
    .addWidget(decorated('From', message.getFrom()))
    .addWidget(decorated('Subject', message.getSubject() || '(no subject)'));

  var card = CardService.newCardBuilder()
    .addSection(wordmarkSection())
    .addSection(verdict)
    .addSection(reasons);
  if (aiSection) card.addSection(aiSection);
  if (result.mode !== 'organization') card.addSection(buildPersonalReportSection());
  card.addSection(email);
  if (result.reasons.length > 0) card.addSection(buildDetailsSection(result.reasons));
  if (result.mode === 'organization') {
    // Last, right above the footer button it explains.
    card.addSection(
      CardService.newCardSection().addWidget(CardService.newTextParagraph().setText(REPORT_NOTE))
    );
    card.setFixedFooter(buildReportFooter(message, result));
  }
  return card.build();
}

/** A card image served by our backend (fixed files, never from an email). */
function cardImage(name, altText) {
  return CardService.newImage()
    .setImageUrl(BACKEND_BASE_URL + '/static/' + name + '.png?v=' + ASSET_VERSION)
    .setAltText(altText);
}

/** "SUSPICIOUS" in its color: the word carries the verdict, the color only adds to it. */
function verdictWord(ui) {
  return '<font color="' + ui.color + '"><b>' + ui.word.toUpperCase() + '</b></font>';
}

/**
 * "■■■■■□□□□□  52/100 · Suspicious": filled squares read without color, the number
 * is exact, and the verdict word stays in text in case the banner doesn't load.
 */
function scoreLine(score, ui) {
  var filled = Math.round(score / 10);
  return (
    '<font color="' + ui.color + '">' + repeat('■', filled) + '</font>' +
    repeat('□', 10 - filled) + '  <b>' + score + '</b>/100 · ' + ui.word
  );
}

function repeat(text, count) {
  return new Array(count + 1).join(text);
}

/**
 * "▲ High risk" in the severity's color, plus " · AI check" in the AI color for
 * reasons only the AI check found; empty without a known severity. The shape and
 * word carry the meaning, the color only adds to it. Labels come from fixed maps,
 * never the backend.
 */
function reasonLabel(reason) {
  var word = SEVERITY_WORDS[reason.severity];
  if (!word) return '';
  var label = colored(SEVERITY_MARKS[reason.severity] + ' ' + word, SEVERITY_COLORS[reason.severity]);
  return reason.fromAi ? label + ' · ' + colored('AI check', AI_COLOR) : label;
}

/** Fixed text in a color; never used on untrusted text. */
function colored(text, color) {
  return '<font color="' + color + '">' + text + '</font>';
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
  found = found.map(function (line) {
    return colored('<b>' + toPlainText(line) + '</b>', AI_COLOR);
  });
  if (found.length === 0) return [toPlainText('The AI check read this email and found no pressure tactics.')];
  return [toPlainText('The AI check read this email and found:')].concat(found);
}

/** "🤖 AI check" section, so the user sees the AI took part and what it found. */
function buildAiSection(ai) {
  var lines = aiLines(ai);
  if (lines.length === 0) return null;
  var section = CardService.newCardSection().setHeader('🤖 AI check');
  // aiLines() escapes its fixed wording itself and adds the color markup.
  lines.forEach(function (line) {
    section.addWidget(CardService.newTextParagraph().setText(line));
  });
  return section;
}

/**
 * Personal mode: there is no security team, so point to Gmail's own "Report
 * phishing" (US-13, ADR-015). Organization mode has the Report button in the
 * fixed footer instead (US-06, ADR-008). Both shown for every verdict: the user may spot
 * something the checks missed.
 */
function buildPersonalReportSection() {
  var section = CardService.newCardSection().setHeader('Think this email is a scam?');
  PERSONAL_REPORT_LINES.forEach(function (line) {
    section.addWidget(CardService.newTextParagraph().setText(line));
  });
  return section;
}

/**
 * The Report button in a fixed footer, always in view. Gmail right-aligns footer
 * buttons and draws no Columns in the side panel, so it can't be centered.
 */
function buildReportFooter(message, result) {
  return CardService.newFixedFooter().setPrimaryButton(
    CardService.newTextButton()
      .setText('Report to Security Team')
      // Set here: the top bar is white, and the button would take its color.
      .setBackgroundColor(REPORT_BUTTON_COLOR)
      .setOnClickAction(
        CardService.newAction()
          .setFunctionName('onReport')
          .setParameters(reportParameters(message.getId(), result))
      )
  );
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

/** Shown after a report is delivered (US-06: confirmation after reporting; ADR-014 wording). */
function buildReportedCard() {
  var section = CardService.newCardSection()
    .addWidget(
      CardService.newDecoratedText()
        .setTopLabel('✅ Report sent')
        .setText('<b>Thanks, the security team has been notified.</b>')
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
    CardService.newCardHeader()
      .setTitle('WindyMail')
      .setSubtitle(subtitle)
      .setImageUrl(LOGO_URL)
      .setImageStyle(CardService.ImageStyle.CIRCLE)
      .setImageAltText('WindyMail')
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
