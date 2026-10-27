/**
 * Add-on configuration. Not secret: the backend URL is public and must also be
 * listed in appsscript.json "urlFetchWhitelist" (change both together).
 */
var BACKEND_BASE_URL = 'https://windymail-backend.onrender.com';

/** The add-on logo, shown in card headers; same as "logoUrl" in appsscript.json. */
var LOGO_URL = 'https://www.gstatic.com/images/icons/material/system/2x/air_googblue_48dp.png';

/** Bump when a card image in backend/static changes, so Gmail's image cache refreshes. */
var ASSET_VERSION = '2';

/** Upper bounds matching the backend request schema (backend/app/models.py). */
var LIMITS = {
  from: 1000,
  replyTo: 1000,
  subject: 2000,
  authResults: 10000,
  bodyText: 100000,
  bodyHtml: 150000,
  attachments: 50,
  filename: 512,
  mimeType: 255,
};

/**
 * Serialized request budget in UTF-8 bytes, below the backend's 200 KB limit
 * (ADR-011). Bodies are trimmed to fit: HTML first, then plain text.
 */
var MAX_REQUEST_BYTES = 190000;

/** Display cap for any single untrusted value shown in a card. */
var MAX_DISPLAY_CHARS = 200;
