"""
webhook_catcher/app.py

This file runs on Railway (a free cloud hosting service).
It is the ONLY piece of this project that lives in the cloud.

Its entire job is simple:
  - Wait for Instagram to tell us someone left a comment
  - Verify the request genuinely came from Meta (HMAC-SHA256 signature check)
  - Save that comment to our Supabase queue
  - Reply "ok" immediately so Instagram doesn't retry

It does NOT reply to anyone. It does NOT use AI.
It is just a tiny post box that catches messages and stores them.

Security measures applied:
  - Rate limiting (flask-limiter): 500 req/min on webhook POST, 20/min on
    verification GET, 60/min on /ping and /health
  - 512 KB request body cap (MAX_CONTENT_LENGTH)
  - HMAC-SHA256 signature verification on every POST using META_APP_SECRET
  - sender_id validated as numeric string before touching the database
  - Comment text truncated to 2200 chars and null bytes stripped
  - Content-Type: application/json enforced on webhook POST
"""

import os
import re
import hmac
import hashlib
import logging
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from supabase import create_client

app = Flask(__name__)

# Reject bodies larger than 512 KB — Meta webhook payloads are tiny JSON blobs.
# This prevents memory exhaustion from oversized or malicious requests.
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Rate limiter — tracks requests per IP address, stored in memory.
# Prevents anyone from flooding our endpoint with fake webhook calls
# that would fill up the Supabase queue with garbage.
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")

# Supabase client is created lazily on first use so the app can start
# even if Railway hasn't injected env vars yet at import time.
_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _supabase = create_client(url, key)
    return _supabase


# Instagram user IDs are always numeric strings (up to ~20 digits).
# Anything else is invalid and should be rejected before touching the queue.
_SENDER_ID_RE = re.compile(r"^\d{1,30}$")

# Hard caps on how much data we'll process per incoming payload.
# Meta sends at most a handful of entries per webhook call in practice.
_MAX_ENTRIES  = 25
_MAX_CHANGES  = 25
_MAX_COMMENT  = 2200   # characters — above Instagram's own display limit


# ── Meta webhook verification ─────────────────────────────────────────────────

@app.route("/webhook/instagram", methods=["GET"])
@limiter.limit("20 per minute")
def instagram_verify():
    """
    One-time handshake with Meta (Instagram's parent company).

    When you first register your webhook URL in the Meta Developer dashboard,
    Meta sends a GET request here to confirm the URL belongs to you.
    We check that the verify_token matches what we set as VERIFY_TOKEN in Railway.
    If it matches, we send back a challenge code — Meta considers the
    webhook verified and starts sending real comment events.

    This only runs once during initial setup, not on every comment.
    Rate-limited to 20 requests/minute to prevent brute-forcing the verify token.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and token == os.getenv("VERIFY_TOKEN"):
        log.info("✅ Instagram webhook verified by Meta")
        return challenge, 200

    log.warning("❌ Webhook verification failed — token mismatch")
    return "Forbidden", 403


# ── Instagram comment events ──────────────────────────────────────────────────

@app.route("/webhook/instagram", methods=["POST"])
@limiter.limit("500 per minute")
def instagram_webhook():
    """
    Receives a notification every time someone comments on your Instagram post.

    Instagram sends us a JSON package containing:
      - who left the comment (their user ID)
      - what they wrote

    Security checks performed (in order):
      1. Content-Type must be application/json — reject anything else
      2. HMAC-SHA256 signature is verified against META_APP_SECRET
      3. sender_id must be a numeric string (no injection payloads)
      4. comment text is truncated and null bytes stripped

    We must reply with HTTP 200 within a few seconds — if we don't,
    Instagram assumes something went wrong and keeps retrying.
    """
    # Meta always sends Content-Type: application/json.
    # Reject non-JSON requests before doing any further processing.
    if not request.is_json:
        log.warning("❌ Non-JSON Content-Type — ignoring request")
        return "Bad Request", 400

    if not _valid_meta_signature(request):
        log.warning("❌ Invalid Meta signature — ignoring request")
        return "Unauthorized", 401

    data = request.get_json(silent=True) or {}
    log.info("📨 Instagram comment event received")

    entries = data.get("entry", [])
    if not isinstance(entries, list):
        return jsonify({"status": "ok"}), 200

    for entry in entries[:_MAX_ENTRIES]:
        changes = entry.get("changes", [])
        if not isinstance(changes, list):
            continue

        for change in changes[:_MAX_CHANGES]:
            if change.get("field") != "comments":
                continue

            value        = change.get("value", {})
            comment_text = str(value.get("text", "")).strip()
            sender_id    = str(value.get("from", {}).get("id", "")).strip()

            if not comment_text or not sender_id:
                continue

            # Reject sender IDs that aren't plain numeric strings.
            # Real Instagram user IDs are always digits only.
            if not _SENDER_ID_RE.match(sender_id):
                log.warning(f"⚠️  Invalid sender_id format: {sender_id!r} — skipping")
                continue

            # Truncate to a safe length and strip null bytes before storing.
            comment_text = comment_text[:_MAX_COMMENT].replace("\x00", "")

            _queue_event("instagram", sender_id, comment_text)

    return jsonify({"status": "ok"}), 200


# ── UptimeRobot keep-warm endpoint ────────────────────────────────────────────

@app.route("/ping", methods=["GET"])
@limiter.limit("60 per minute")
def ping():
    """
    A simple 'are you awake?' endpoint used by UptimeRobot.

    Free hosting services like Railway automatically shut down your server
    after a period of inactivity to save resources. When the next real
    request arrives, there is a cold-start delay of several seconds.

    UptimeRobot (a free service) pings this URL every 5 minutes to keep
    the server awake — so when Instagram sends a comment event, the server
    is always ready to receive it instantly with no delay.

    Setup: uptimerobot.com → Add Monitor → HTTP → your Railway URL + /ping
    """
    return jsonify({"status": "ok", "message": "pong"}), 200


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
@limiter.limit("60 per minute")
def health():
    """
    A simple status check endpoint.
    Visit this URL in your browser to confirm the server is running correctly.
    Useful for monitoring and debugging.
    """
    return jsonify({
        "status":  "ok",
        "service": "local-llm-autoreply webhook catcher",
        "version": "3.0.0"
    }), 200


# ── Helper functions ──────────────────────────────────────────────────────────

def _queue_event(platform: str, sender_id: str, content: str):
    """
    Saves an incoming comment event to the Supabase queue table.

    Think of this as dropping a sticky note into a to-do tray.
    The local worker on your laptop picks it up later, generates a reply
    using Ollama, and sends it. Until then the note sits safely in the queue.

    Each saved row contains:
      - platform:  where the event came from ('instagram')
      - sender_id: who sent it (Instagram user ID)
      - content:   what they wrote (the comment text)
      - processed: false — meaning it hasn't been replied to yet
    """
    try:
        get_supabase().table("queue").insert({
            "platform":  platform,
            "sender_id": sender_id,
            "content":   content,
            "processed": False
        }).execute()
        log.info(f"✅ Queued {platform} event from {sender_id}")
    except Exception as e:
        log.error(f"❌ Failed to queue event: {e}")


def _valid_meta_signature(req) -> bool:
    """
    Checks that an incoming request genuinely came from Meta (Instagram).

    Anyone on the internet could send a fake POST request to our webhook URL.
    To prevent this, Meta signs every request it sends using our app secret —
    like a wax seal on an envelope. We verify that seal before trusting the content.

    META_APP_SECRET is read fresh from the environment on every request so that
    credential rotation (changing the env var) takes effect without a restart.

    If META_APP_SECRET is not set as an environment variable, we skip this check.
    Only acceptable in local development — always set it in production.
    """
    secret = os.getenv("META_APP_SECRET")
    if not secret:
        log.warning("⚠️  META_APP_SECRET not set — skipping signature check (dev mode only)")
        return True

    sig = req.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False

    expected = hmac.new(
        secret.encode(),
        req.get_data(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(sig[7:], expected)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Webhook catcher running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
