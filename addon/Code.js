/**
 * WindyMail Gmail add-on.
 *
 * Thin client (ADR-001): reads the opened message, renders cards, handles actions.
 * No scoring logic and no secrets live here. UI is CardService only (ADR-002).
 */

var MAX_DISPLAY_CHARS = 200;

/** Homepage trigger: shown when the add-on is opened with no message selected. */
function onHomepage(e) {
  var section = CardService.newCardSection().addWidget(
    CardService.newTextParagraph().setText('Open an email to check whether it is safe.')
  );
  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('WindyMail'))
    .addSection(section)
    .build();
}

/** Contextual trigger: runs when the user opens a message. */
function onGmailMessageOpen(e) {
  GmailApp.setCurrentMessageAccessToken(e.gmail.accessToken);
  var message = GmailApp.getMessageById(e.gmail.messageId);

  var section = CardService.newCardSection()
    .addWidget(decorated('From', message.getFrom()))
    .addWidget(decorated('Subject', message.getSubject() || '(no subject)'))
    .addWidget(decorated('Score', 'Not checked yet (placeholder)'));

  return CardService.newCardBuilder()
    .setHeader(CardService.newCardHeader().setTitle('WindyMail').setSubtitle('Email check'))
    .addSection(section)
    .build();
}

/** A label/value row. The value is untrusted, so it is escaped and truncated. */
function decorated(label, value) {
  return CardService.newDecoratedText()
    .setTopLabel(label)
    .setText(toPlainText(value))
    .setWrapText(true);
}

/**
 * CardService text widgets interpret basic HTML (<a>, <b>, <font>). Email fields
 * are attacker-controlled, so escape them to keep them inert plain text (ADR-002).
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
