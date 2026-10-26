/**
 * WindyMail Gmail add-on: trigger and action entry points.
 *
 * Thin client (ADR-001): reads the opened message, calls the backend, renders cards.
 * No scoring logic and no secrets live here.
 */

/** Homepage trigger: shown when the add-on is opened with no message selected. */
function onHomepage(e) {
  return buildHomepageCard();
}

/** Contextual trigger: runs when the user opens a message. */
function onGmailMessageOpen(e) {
  GmailApp.setCurrentMessageAccessToken(e.gmail.accessToken);
  var message = GmailApp.getMessageById(e.gmail.messageId);

  var result = analyzeMessage(message);
  return result ? buildResultCard(message, result) : buildErrorCard();
}

/** "Try again" button on the error card: re-runs the check in place. */
function onRetry(e) {
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(onGmailMessageOpen(e)))
    .build();
}
