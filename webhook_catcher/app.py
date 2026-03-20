"""
webhook_catcher/app.py

This file runs on Railway or Render (a free cloud hosting service).
It is the ONLY piece of this project that lives in the cloud.

Its entire job is simple:
  - Wait for Instagram to tell us someone left a comment
  - Save that comment to our Supabase queue
  - Reply "ok" immediately so Instagram doesn't retry

It does NOT reply to anyone. It does NOT use AI.
It is just a tiny post box that catches messages and stores them.
"""

import os
import hmac
import hashlib
import logging
from flask import Flask, request, jsonify
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
APP_SECRET   = os.getenv("META_APP_SECRET")


# ── Meta webhook verification ─────────────────────────────────────────────────

@app.route("/webhook/instagram", methods=["GET"])
def instagram_verify():
    """
    One-time handshake with Meta (Instagram's parent company).

    When you first register your webhook URL in the Meta Developer dashboard,
    Meta sends a GET request here to confirm the URL belongs to you.
    We check that the verify_token matches what we set in .env.
    If it matches, we send back a challenge code — Meta considers the
    webhook verified and starts sending real comment events.

    This only runs once during initial setup, not on every comment.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        log.info("✅ Instagram webhook verified by Meta")
        return challenge, 200

    log.warning("❌ Webhook verification failed — token mismatch")
    return "Forbidden", 403


# ── Instagram comment events ──────────────────────────────────────────────────

@app.route("/webhook/instagram", methods=["POST"])
def instagram_webhook():
    """
    Receives a notification every time someone comments on your Instagram post.

    Instagram sends us a JSON package containing:
      - who left the comment (their user ID)
      - what they wrote

    We first verify the request is genuinely from Meta (not a fake/spoofed request).
    Then we extract the comment text and commenter's ID.
    Finally we save it to Supabase for the local worker to process later.

    We must reply with HTTP 200 within a few seconds — if we don't,
    Instagram assumes something went wrong and keeps retrying.
    """
    if not _valid_meta_signature(request):
        log.warning("❌ Invalid Meta signature — ignoring request")
        return "Unauthorized", 401

    data = request.get_json(silent=True) or {}
    log.info("📨 Instagram comment event received")

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue

            value        = change.get("value", {})
            comment_text = value.get("text", "").strip()
            sender_id    = value.get("from", {}).get("id")

            if not comment_text or not sender_id:
                continue

            _queue_event("instagram", sender_id, comment_text)

    return jsonify({"status": "ok"}), 200


# ── UptimeRobot keep-warm endpoint ────────────────────────────────────────────

@app.route("/ping", methods=["GET"])
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
        supabase.table("queue").insert({
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

    If META_APP_SECRET is not set in .env, we skip this check.
    Only skip in development — always set it in production.
    """
    if not APP_SECRET:
        log.warning("⚠️  META_APP_SECRET not set — skipping signature check (dev mode only)")
        return True

    sig = req.headers.get("X-Hub-Signature-256", "")
    if not sig.startswith("sha256="):
        return False

    expected = hmac.new(
        APP_SECRET.encode(),
        req.get_data(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(sig[7:], expected)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log.info(f"🚀 Webhook catcher running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
