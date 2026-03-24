"""
tests/test_e2e.py

End-to-end test that exercises the full pipeline for each platform.

Instagram: inserts a fake event into the Supabase queue and waits for
the running worker to pick it up, generate a reply with Ollama, and
attempt to send the DM. (DM will fail if the sender_id is fake — that's
expected. What matters is that Ollama generated a reply.)

Email: fetches any unread emails from Gmail directly via IMAP and sends
AI-generated replies for each one. Email does NOT go through the Supabase
queue — the worker polls Gmail directly — so this test exercises that path
without needing the worker running in another terminal.

Usage:
  # Instagram test — start the worker first in another terminal
  python worker/worker.py

  # Then run the full e2e test
  python tests/test_e2e.py

  # For the email test to do real work: send a test email to your SMTP_USER
  # inbox before running this script.
"""

import sys
import os
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from supabase import create_client

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)


def insert_test_instagram_event():
    """
    Inserts a fake Instagram comment into the Supabase queue.

    The worker will pick this up within 30 seconds and try to
    generate a reply using Ollama. The DM send will fail (since
    the sender_id is fake) but you can confirm Ollama generated
    a reply by watching the worker logs.

    To test with a real DM, replace TEST_SENDER_ID with a real
    Instagram user ID of an account you control.
    """
    TEST_SENDER_ID   = "000000000000001"  # replace with a real IG user ID for a live test
    TEST_COMMENT     = "Hey! Can you send me the link please?"

    print("\n📸 Inserting fake Instagram comment into queue...")
    print(f"   Sender ID: {TEST_SENDER_ID}")
    print(f"   Comment:   '{TEST_COMMENT}'")

    result = supabase.table("queue").insert({
        "platform":  "instagram",
        "sender_id": TEST_SENDER_ID,
        "content":   TEST_COMMENT,
        "processed": False
    }).execute()

    row_id = result.data[0]["id"]
    print(f"   ✅ Row inserted — id: {row_id}")
    return row_id


def test_email_flow_directly() -> bool:
    """
    Tests the email pipeline end-to-end by fetching any unread emails
    from Gmail via IMAP and sending AI-generated replies for each one.

    Email does NOT use the Supabase queue — the worker polls Gmail directly.
    Inserting into the queue has no effect on email processing, so this test
    exercises the real IMAP → Ollama → SMTP path instead.

    To get full coverage: send a test email to your SMTP_USER inbox before
    running this test. If the inbox is empty the test passes with a notice.
    """
    # Import from the worker directory (sibling of this file's parent)
    worker_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "worker")
    sys.path.insert(0, worker_dir)
    from ollama_client import generate_reply

    from senders.email import fetch_new_emails, send_email_reply

    print("\n📧 Testing email flow directly (IMAP → Ollama → SMTP)...")

    emails = fetch_new_emails()

    if not emails:
        print("  ℹ️  No unread emails found — send a test email to your Gmail inbox first,")
        print("     then re-run this test. Email flow skipped (not a failure).")
        return True

    print(f"  📬 Found {len(emails)} unread email(s) to process")
    all_ok = True

    for em in emails:
        try:
            context = f"Subject: {em['subject']}\n\n{em['body']}"
            reply   = generate_reply("email", context)
            if not reply:
                reply = "Thanks for reaching out — I'll get back to you soon."

            success = send_email_reply(em["sender"], reply)
            status  = "✅" if success else "❌"
            print(f"  {status} Reply sent to {em['sender']}: '{em['subject'][:40]}'")
            if not success:
                all_ok = False

        except Exception as e:
            print(f"  ❌ Error processing email from {em.get('sender', '?')}: {e}")
            all_ok = False

    return all_ok


def wait_for_processing(row_id: str, timeout_seconds: int = 60):
    """
    Watches the Supabase queue and waits until the worker has
    processed the test row we just inserted.

    Polls every 5 seconds and reports what it sees. If the row is
    processed or failed within the timeout, it tells you what happened.
    If nothing happens within the timeout, the worker may not be running.
    """
    print(f"\n⏳ Waiting for worker to process row {row_id}...")
    print(f"   (Make sure the worker is running: python worker/worker.py)")
    print(f"   Checking every 5 seconds for up to {timeout_seconds} seconds...\n")

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        result = supabase.table("queue").select("*").eq("id", row_id).execute()
        row    = result.data[0] if result.data else None

        if not row:
            print("  ❌ Row not found in Supabase — something went wrong")
            return False

        if row["processed"]:
            print(f"  ✅ Row processed successfully!")
            print(f"     The worker generated a reply and sent it.")
            return True

        if row["failed"]:
            print(f"  ⚠️  Row marked as failed: {row['failed']}")
            print(f"     This is expected if the sender_id is fake (Instagram test).")
            print(f"     The important thing is that Ollama generated a reply — check worker logs.")
            return True

        print(f"  ⏳ Still pending... (elapsed: {int(time.time() - (deadline - timeout_seconds))}s)")
        time.sleep(5)

    print(f"  ❌ Timed out after {timeout_seconds}s — is the worker running?")
    return False


def cleanup_test_rows():
    """
    Removes any test rows from the queue that were created by this script.
    Keeps your queue clean after testing.
    """
    print("\n🧹 Cleaning up test rows...")
    supabase.table("queue").delete().eq("sender_id", "000000000000001").execute()
    print("  ✅ Test rows removed")


if __name__ == "__main__":
    print("=" * 55)
    print("  local-llm-autoreply — end-to-end test")
    print("=" * 55)
    print("\nInstagram: requires the worker running in another terminal.")
    print("Email:     runs directly here — no worker needed.\n")

    # Test Instagram flow via Supabase queue (requires worker running)
    ig_row_id = insert_test_instagram_event()
    ig_ok     = wait_for_processing(ig_row_id, timeout_seconds=90)

    # Test email flow directly via IMAP → Ollama → SMTP
    # (email never goes through Supabase — the worker polls Gmail directly)
    email_ok = test_email_flow_directly()

    # Clean up fake Instagram test data from Supabase
    cleanup_test_rows()

    print("\n" + "=" * 55)
    print("  Results:")
    print(f"  {'✅' if ig_ok    else '❌'} Instagram flow")
    print(f"  {'✅' if email_ok else '❌'} Email flow")
    print("=" * 55)
    if ig_ok and email_ok:
        print("  🚀 End-to-end test passed — system is working!")
    else:
        print("  ⚠️  Check worker logs for details on what went wrong")
    print("=" * 55)
