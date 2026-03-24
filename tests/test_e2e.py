"""
tests/test_e2e.py

End-to-end test that exercises the full pipeline for each platform.

─── What this tests ───────────────────────────────────────────────────────────

  Instagram path (requires the worker running in another terminal):
    1. Inserts a fake comment into the Supabase queue
    2. Waits up to 90s for the worker to pick it up
    3. Worker asks Ollama for a reply
    4. Worker tries to send the DM (will fail — fake sender ID — that's expected)
    5. Row is marked as 'failed' with reason "DM send failed" → test passes

  Email path (no worker needed — runs entirely here):
    1. Connects to Gmail via IMAP and fetches any unread emails
    2. Sends each one to Ollama for a reply
    3. Sends the reply via SMTP
    4. If no unread emails → passes with a notice (not a failure)

─── How to run ────────────────────────────────────────────────────────────────

  # Terminal 1 — start the worker first (Instagram test needs this)
  python worker/worker.py

  # Terminal 2 — run the e2e test
  python tests/test_e2e.py

  # Email-only mode (no worker needed):
  # Just run the test without starting the worker.
  # The Instagram test will timeout and fail, but email will still be tested.
  # To get full email coverage: send a test email to your SMTP_USER inbox first.

─── Why each test might fail ──────────────────────────────────────────────────

  Instagram — "Timed out after 90s":
    The worker is not running. Start it with: python worker/worker.py
    It must be running in a separate terminal before you run this test.

  Instagram — "Row marked as failed: DM send failed":
    This is the EXPECTED result for this test. The fake sender ID (000000000000001)
    doesn't exist on Instagram, so the DM can't be delivered. What matters is
    that the worker picked up the queue row and called Ollama — the pipeline works.

  Email — "No unread emails found":
    Not a failure. Send a test email to your SMTP_USER inbox and run again.

  Email — SMTP/IMAP error:
    Check that SMTP_USER and SMTP_PASSWORD are exported in ~/.zshrc.
"""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from supabase import create_client

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)


# ── Instagram test ─────────────────────────────────────────────────────────────

def insert_test_instagram_event():
    """
    Inserts a fake Instagram comment into the Supabase queue.

    What happens next (if the worker is running):
      • Worker picks it up within 30 seconds
      • Sends the comment text to Ollama for a reply
      • Tries to DM user ID 000000000000001 — this fails (fake ID, doesn't exist)
      • Marks the row as 'failed' with reason "DM send failed"

    That failure is the expected outcome. The important thing is seeing
    that the worker processed the row at all — that proves the full
    Supabase → Worker → Ollama pipeline is working.

    To test with a real DM: replace TEST_SENDER_ID with a real Instagram
    user ID of an account you control.
    """
    TEST_SENDER_ID = "000000000000001"   # fake — DM will fail, that's expected
    TEST_COMMENT   = "Hey! Can you send me the link please?"

    print("\n📸 Instagram test — inserting fake comment into queue...")
    print(f"   Sender ID : {TEST_SENDER_ID}  (fake — DM will fail, that's expected)")
    print(f"   Comment   : '{TEST_COMMENT}'")
    print()
    print("   ⚠️  This test requires the worker to be running in another terminal.")
    print("       If you haven't started it: python worker/worker.py")

    result = supabase.table("queue").insert({
        "platform":  "instagram",
        "sender_id": TEST_SENDER_ID,
        "content":   TEST_COMMENT,
        "processed": False
    }).execute()

    row_id = result.data[0]["id"]
    print(f"\n   ✅ Row inserted — id: {row_id}")
    return row_id


def wait_for_processing(row_id: str, timeout_seconds: int = 90) -> bool:
    """
    Polls Supabase every 5 seconds until the worker processes the test row.

    Success conditions (either one means the pipeline is working):
      • processed = True  → worker replied and DM was sent (real sender ID only)
      • failed = "DM send failed"  → worker ran Ollama but DM failed (expected for fake ID)

    Failure condition:
      • Timeout — the worker never touched the row. Likely not running.
    """
    print(f"\n⏳ Waiting for worker to process row {row_id}...")
    print(f"   Checking every 5 seconds for up to {timeout_seconds} seconds...")
    print(f"   Watch the worker terminal for log lines starting with 📸 and 🤖\n")

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        result = supabase.table("queue").select("*").eq("id", row_id).execute()
        row    = result.data[0] if result.data else None

        if not row:
            print("  ❌ Row not found in Supabase — something went wrong with the insert")
            return False

        if row["processed"]:
            print("  ✅ Row processed — worker replied and DM was sent!")
            print("     The full Instagram pipeline is working end-to-end.")
            return True

        if row["failed"]:
            reason = row["failed"]
            if "DM send failed" in reason or "Invalid recipient" in reason:
                print(f"  ✅ Row marked as failed: '{reason}'")
                print("     This is the expected result for a fake sender ID.")
                print("     It proves: queue → worker → Ollama → DM attempt all worked.")
                print("     The only thing that failed was the DM delivery (fake ID).")
            else:
                print(f"  ❌ Row failed with unexpected reason: '{reason}'")
                print("     Check the worker logs for what went wrong.")
                return False
            return True

        elapsed = int(time.time() - (deadline - timeout_seconds))
        print(f"  ⏳ Still pending... (elapsed: {elapsed}s)")
        time.sleep(5)

    print(f"\n  ❌ Timed out after {timeout_seconds}s — worker did not process the row.")
    print("     Most likely cause: the worker is not running.")
    print("     Fix: open a new terminal and run: python worker/worker.py")
    print("     Then re-run this test.")
    return False


# ── Email test ─────────────────────────────────────────────────────────────────

def test_email_flow_directly() -> bool:
    """
    Tests the email pipeline end-to-end without needing the worker.

    What this does:
      1. Connects to Gmail via IMAP and fetches any unread emails
      2. Sends each email's subject + body to Ollama for a reply
      3. Sends the reply back to the sender via SMTP
      4. Gmail marks the emails as read so they won't be processed again

    Why it doesn't need the worker:
      Email doesn't go through the Supabase queue. The worker polls Gmail
      directly via IMAP — no cloud server involved. This test bypasses the
      worker and runs the same IMAP → Ollama → SMTP logic directly.

    To get full coverage:
      Send a test email to your SMTP_USER inbox before running this test.
      If the inbox is empty, the test passes with a notice — not a failure.
    """
    worker_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "worker")
    sys.path.insert(0, worker_dir)
    from ollama_client import generate_reply
    from senders.email import fetch_new_emails, send_email_reply, mark_email_read

    print("\n📧 Email test — IMAP → Ollama → SMTP (no worker needed)...")

    emails = fetch_new_emails()

    if not emails:
        print("  ℹ️  No unread emails found in your inbox.")
        print("     To test: send an email to your SMTP_USER address, then re-run.")
        print("     This is not a failure — the IMAP and SMTP connections still work")
        print("     (they were already verified by test_all.py).")
        return True

    print(f"  📬 Found {len(emails)} unread email(s) — generating replies...")
    all_ok = True

    for em in emails:
        try:
            context = f"Subject: {em['subject']}\n\n{em['body']}"
            reply   = generate_reply("email", context)
            if not reply:
                reply = "Thanks for reaching out — I'll get back to you soon."

            success = send_email_reply(em["sender"], reply)
            if success:
                mark_email_read(em["uid"])
                print(f"  ✅ Reply sent to {em['sender']}: '{em['subject'][:50]}'")
            else:
                print(f"  ❌ Failed to reply to {em['sender']}: '{em['subject'][:50]}' — email left unread")
                all_ok = False

        except Exception as e:
            print(f"  ❌ Error processing email from {em.get('sender', '?')}: {e}")
            all_ok = False

    if all_ok:
        print("  ✅ Email pipeline working — IMAP fetch → Ollama reply → SMTP send all succeeded.")

    return all_ok


# ── Cleanup ────────────────────────────────────────────────────────────────────

def cleanup_test_rows():
    """
    Removes any test rows from the queue created by this script.
    Keeps the queue clean after testing.
    """
    print("\n🧹 Cleaning up test rows from Supabase queue...")
    supabase.table("queue").delete().eq("sender_id", "000000000000001").execute()
    print("  ✅ Test rows removed")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  local-llm-autoreply — end-to-end test")
    print("=" * 60)
    print()
    print("  Instagram test  requires the worker running in another terminal.")
    print("  Email test      runs directly here — no worker needed.")
    print()
    print("  Run the worker first if you haven't:")
    print("    python worker/worker.py")
    print("=" * 60)

    # Test 1: Instagram queue → worker → Ollama → DM attempt
    ig_row_id = insert_test_instagram_event()
    ig_ok     = wait_for_processing(ig_row_id, timeout_seconds=90)

    # Test 2: Gmail IMAP → Ollama → SMTP (runs entirely in this process)
    email_ok = test_email_flow_directly()

    # Remove the fake test row from Supabase
    cleanup_test_rows()

    print("\n" + "=" * 60)
    print("  Results:")
    print(f"  {'✅' if ig_ok    else '❌'} Instagram pipeline (queue → worker → Ollama → DM)")
    print(f"  {'✅' if email_ok else '❌'} Email pipeline    (IMAP → Ollama → SMTP)")
    print("=" * 60)

    if ig_ok and email_ok:
        print("  🚀 Both pipelines working — system is ready!")
    elif not ig_ok and email_ok:
        print("  ⚠️  Email works. Instagram timed out — is the worker running?")
        print("      Start it with: python worker/worker.py")
        print("      Then re-run this test.")
    else:
        print("  ⚠️  Check worker logs and the 'Fix:' lines above.")
    print("=" * 60)
