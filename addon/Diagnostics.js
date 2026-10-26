/**
 * One-time setup helper, run manually from the Apps Script editor.
 *
 * Prints only the "aud" (audience) claim of this script's identity token: the
 * OAuth client ID the backend must expect in GOOGLE_CLIENT_ID (ADR-011). The
 * token itself is never logged.
 */
function logTokenAudience() {
  var token = ScriptApp.getIdentityToken();
  if (!token) {
    console.log('No identity token. Is the openid scope authorized?');
    return;
  }
  var payload = token.split('.')[1];
  var padded = payload + '==='.slice((payload.length + 3) % 4);
  var claims = JSON.parse(
    Utilities.newBlob(Utilities.base64DecodeWebSafe(padded)).getDataAsString()
  );
  console.log('aud: ' + claims.aud);
}
