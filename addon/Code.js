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

/**
 * "Report to Security Team" button (organization mode). The parameters come from
 * the card we built, and the backend checks them again.
 */
function onReport(e) {
  var p = e.parameters || {};
  var score = Number(p.score);
  var reasonIds = p.reasonIds ? String(p.reasonIds).split(',') : [];

  if (!reportMessage(p.messageId, score, reasonIds)) {
    return CardService.newActionResponseBuilder()
      .setNotification(
        CardService.newNotification().setText("Couldn't send the report. Please try again in a moment.")
      )
      .build();
  }
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(buildReportedCard()))
    .build();
}

/** "Try again" button on the error card: re-runs the check in place. */
function onRetry(e) {
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().updateCard(onGmailMessageOpen(e)))
    .build();
}
