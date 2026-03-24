"""
worker/worker.py

This is the brain of the whole system. It runs on YOUR LOCAL MACHINE.

Every 30 seconds it checks Supabase for new Instagram comments to reply to.
Every 2 minutes it checks Gmail directly for new unread emails.

For each new comment or email, it:
  1. Sends the content to Ollama (your local AI)
  2. Gets a generated reply back
  3. Sends the reply via Instagram DM or email
  4. Marks the item as done

If Ollama is offline or fails, it sends a safe fallback reply instead
so the person always gets a response — never silence.

Start this with: python worker/worker.py
Keep it running in a terminal while you want auto-replies active.
"""

import sys
import os
from pathlib import Path

# Add the project root to sys.path so the 'senders' package can be found.
# Without this, running 'python worker/worker.py' from the project root sets
# sys.path[0] to the worker/ directory, making 'from senders.x import ...' fail.
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import logging
from supabase import create_client
from ollama_client import generate_reply, check_ollama_health
from senders.instagram import send_instagram_dm
from senders.email import send_email_reply, fetch_new_emails

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

# How often to check for new events (in seconds)
POLL_INTERVAL       = int(os.getenv("POLL_INTERVAL_SECONDS", 30))       # Instagram queue
EMAIL_POLL_INTERVAL = int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", 120)) # Gmail IMAP

# What to say if Ollama is unavailable — customise these by exporting FALLBACK_INSTAGRAM and FALLBACK_EMAIL in your shell
FALLBACK_REPLIES = {
    "instagram": os.getenv(
        "FALLBACK_INSTAGRAM",
        "Hey! Thanks for your comment 👋 I'll get back to you soon."
    ),
    "email": os.getenv(
        "FALLBACK_EMAIL",
        "Thanks for reaching out! I've received your message and will get back to you shortly.\n\nthenullrabbit"
    ),
}

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# Maps platform names to their send functions
SENDERS = {
    "instagram": send_instagram_dm,
    "email":     send_email_reply,
}


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    """
    The main loop that keeps the worker running indefinitely.

    It wakes up every 30 seconds to check for new Instagram comments,
    and every 2 minutes to check for new emails. Between checks it sleeps
    quietly without using any resources.

    If anything crashes inside a single loop, it logs the error and
    continues — the worker never stops because of a single bad event.
    """
    log.info("🚀 Local worker started")
    log.info(f"⏱️  Instagram: checking Supabase every {POLL_INTERVAL}s")
    log.info(f"📧  Email: checking Gmail every {EMAIL_POLL_INTERVAL}s")
    log.info("💡 Keep this running while your machine is on")

    # Warn if Ollama isn't running yet — fallback replies will be used until it starts
    if not check_ollama_health():
        log.warning("⚠️  Ollama not running — fallback replies will be used until it starts")
        log.warning("   Start Ollama with: ollama serve")

    last_email_poll = 0

    while True:
        try:
            # Check Supabase for new Instagram comments every cycle
            process_instagram_queue()

            # Check Gmail for new emails on a slower cycle
            now = time.time()
            if now - last_email_poll >= EMAIL_POLL_INTERVAL:
                process_new_emails()
                last_email_poll = now

        except Exception as e:
            log.error(f"❌ Worker loop error: {e}")

        time.sleep(POLL_INTERVAL)


# ── Instagram processing ──────────────────────────────────────────────────────

def process_instagram_queue():
    """
    Checks the Supabase queue for unprocessed Instagram comments
    and replies to each one.

    Fetches up to 50 unprocessed rows at a time, oldest first,
    so no comment is ever skipped or replied to twice.
    """
    rows = fetch_unprocessed()

    if not rows:
        log.debug("💤 No pending Instagram events")
        return

    log.info(f"📸 Found {len(rows)} pending Instagram comment(s)")
    for row in rows:
        process_instagram_row(row)


def process_instagram_row(row: dict):
    """
    Handles a single Instagram comment from start to finish.

    Takes the comment text, asks Ollama to generate a reply,
    sends that reply as a DM to the person who commented,
    then marks the queue row as done.

    If anything fails along the way, marks the row as failed
    so it doesn't get retried in an infinite loop.
    """
    row_id    = row["id"]
    sender_id = row["sender_id"]
    content   = row["content"]

    log.info(f"🔄 Instagram comment from {sender_id}: '{content[:60]}'")

    try:
        reply   = _generate_with_fallback("instagram", content)
        success = send_instagram_dm(sender_id, reply)

        if success:
            mark_processed(row_id)
            log.info(f"✅ Instagram row {row_id} done")
        else:
            mark_failed(row_id, "DM send failed")

    except Exception as e:
        log.error(f"❌ Error processing Instagram row {row_id}: {e}")
        mark_failed(row_id, str(e))


# ── Email processing ──────────────────────────────────────────────────────────

def process_new_emails():
    """
    Checks Gmail directly for new unread emails and replies to each one.

    Unlike Instagram (which uses a cloud queue), emails are fetched
    directly from Gmail via IMAP — no cloud server involved.
    The email content never touches Railway or any third party.

    Each email's subject and body are sent to Ollama to generate
    a contextual reply, which is then sent back via SMTP.
    """
    emails = fetch_new_emails()

    if not emails:
        log.debug("💤 No new emails")
        return

    log.info(f"📧 Processing {len(emails)} new email(s)")

    for em in emails:
        try:
            sender  = em["sender"]
            subject = em["subject"]
            body    = em["body"]

            log.info(f"🔄 Email from {sender}: '{subject[:60]}'")

            # Give Ollama both the subject and body for better context
            context = f"Subject: {subject}\n\n{body}"
            reply   = _generate_with_fallback("email", context)
            success = send_email_reply(sender, reply)

            if success:
                log.info(f"✅ Email reply sent to {sender}")
            else:
                log.error(f"❌ Failed to send email reply to {sender}")

        except Exception as e:
            log.error(f"❌ Error processing email: {e}")


# ── Fallback reply ────────────────────────────────────────────────────────────

def _generate_with_fallback(platform: str, content: str) -> str:
    """
    Tries to generate a reply using Ollama. If Ollama is unavailable
    or returns an empty response, returns a safe fallback reply instead.

    This ensures a reply is ALWAYS sent — the sender never gets silence.

    The fallback messages are set as shell environment variables:
      export FALLBACK_INSTAGRAM="Hey! Thanks for your comment..."
      export FALLBACK_EMAIL="Thanks for reaching out..."
    """
    try:
        reply = generate_reply(platform, content)
        if reply and reply.strip():
            log.info(f"🤖 Ollama reply generated ({len(reply)} chars)")
            return reply
        else:
            log.warning("⚠️  Ollama returned empty — using fallback reply")
    except Exception as e:
        log.warning(f"⚠️  Ollama error: {e} — using fallback reply")

    fallback = FALLBACK_REPLIES.get(platform, "Thanks for reaching out! I'll get back to you soon.")
    log.info(f"💬 Using fallback reply for {platform}")
    return fallback


# ── Supabase helpers ──────────────────────────────────────────────────────────

def fetch_unprocessed() -> list[dict]:
    """
    Retrieves all Instagram comment rows from Supabase that haven't
    been replied to yet, ordered by oldest first.

    Skips rows that have already been marked as failed — those won't
    be retried automatically (check the logs to see why they failed).
    """
    result = (
        supabase.table("queue")
        .select("*")
        .eq("platform", "instagram")
        .eq("processed", False)
        .is_("failed", "null")
        .order("created_at")
        .limit(50)
        .execute()
    )
    return result.data or []


def mark_processed(row_id: str):
    """
    Marks a queue row as successfully processed.
    This prevents the same comment from being replied to twice.
    """
    supabase.table("queue").update({"processed": True}).eq("id", row_id).execute()


def mark_failed(row_id: str, reason: str):
    """
    Marks a queue row as failed with a reason explaining what went wrong.
    Failed rows are skipped on future polls — check the logs to investigate.
    Common reasons: DM send failed, Ollama timeout, invalid recipient.
    """
    supabase.table("queue").update({"failed": reason}).eq("id", row_id).execute()


if __name__ == "__main__":
    run()
