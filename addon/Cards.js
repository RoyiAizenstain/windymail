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

var PARTIAL_LINE = "🌫️ Limited visibility: some checks couldn't run. Verdict based on technical signals only.";

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
    reasons.addWidget(CardService.newTextParagraph().setText('• ' + toPlainText(reason.text)));
  });

  var email = CardService.newCardSection()
    .setHeader('Email')
    .addWidget(decorated('From', message.getFrom()))
    .addWidget(decorated('Subject', message.getSubject() || '(no subject)'));

  return newCard('Email check').addSection(verdict).addSection(reasons).addSection(email).build();
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
