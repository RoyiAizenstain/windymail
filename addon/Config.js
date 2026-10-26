/**
 * Add-on configuration. Not secret: the backend URL is public and must also be
 * listed in appsscript.json "urlFetchWhitelist" (change both together).
 */
var BACKEND_BASE_URL = 'https://windymail-backend.onrender.com';

/** Upper bounds matching the backend request schema (backend/app/models.py). */
var LIMITS = {
  from: 1000,
  replyTo: 1000,
  subject: 2000,
};

/** Display cap for any single untrusted value shown in a card. */
var MAX_DISPLAY_CHARS = 200;
