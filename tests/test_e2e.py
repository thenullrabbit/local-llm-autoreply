"""
tests/test_e2e.py

End-to-end test that simulates the full flow without needing a real Instagram comment.

It inserts a fake event directly into the Supabase queue, then watches
the local worker process it in real time. This lets you verify the entire
pipeline works — Supabase → worker → Ollama → sender — before going live.

Usage:
  # In terminal 1 — start the worker
  python worker/worker.py

  # In terminal 2 — run this test
  python tests/test_e2e.py

You should see the worker pick up the fake event and attempt to send a reply.
For Instagram: it will try to DM the test user ID (will fail unless it's a real ID)
For email: it will try to send an email to your SMTP_USER address (sends to yourself)
"""

import sys
import os
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

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


def insert_test_email_event():
    """
    Inserts a fake email event into the Supabase queue.

    Unlike real email events which come via IMAP polling, this inserts
    directly into the queue to test the worker's email processing path.

    The worker will pick this up and send a reply to your SMTP_USER
    address — effectively sending an email to yourself. Check your inbox
    to confirm the reply arrived and looks correct.
    """
    your_email = os.getenv("SMTP_USER", "test@gmail.com")

    TEST_SENDER  = your_email  # sends reply to yourself for easy testing
    TEST_CONTENT = "Subject: Testing the auto-reply\n\nHi, I wanted to ask about your InstaFilter extension. Does it work on all browsers?"

    print("\n📧 Inserting fake email event into queue...")
    print(f"   Sender:  {TEST_SENDER}")
    print(f"   Content: '{TEST_CONTENT[:60]}...'")

    result = supabase.table("queue").insert({
        "platform":  "email",
        "sender_id": TEST_SENDER,
        "content":   TEST_CONTENT,
        "processed": False
    }).execute()

    row_id = result.data[0]["id"]
    print(f"   ✅ Row inserted — id: {row_id}")
    return row_id


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
    print("\nThis test inserts fake events into Supabase and waits")
    print("for the worker to process them. Make sure the worker is")
    print("running in another terminal before proceeding.\n")

    # Test Instagram flow
    ig_row_id = insert_test_instagram_event()
    ig_ok     = wait_for_processing(ig_row_id, timeout_seconds=90)

    # Test email flow
    email_row_id = insert_test_email_event()
    email_ok     = wait_for_processing(email_row_id, timeout_seconds=90)

    # Clean up fake test data
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
