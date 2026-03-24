"""
tests/test_all.py

Run this BEFORE starting the worker to check that everything is configured correctly.
It tests each component of the system one by one and tells you exactly what to fix.

Usage:
  source ~/.zshrc
  python tests/test_all.py

A healthy system shows all green ticks. Fix any red crosses before running the worker.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import imaplib
import smtplib


def test_ollama():
    """
    What this checks:
      1. Ollama is running on your machine (ollama serve)
      2. The correct AI model (default: llama3) has been downloaded (ollama pull llama3)
      3. The model actually responds to a test message

    Why it matters:
      Every auto-reply goes through Ollama. If Ollama is offline, the worker
      falls back to a static reply instead of a personalised AI-generated one.

    If this fails:
      - Start Ollama: ollama serve
      - Download the model: ollama pull llama3
    """
    print("\n🤖 Testing Ollama...")
    try:
        url   = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3")

        resp   = requests.get(f"{url}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]

        if not any(model in m for m in models):
            print(f"  ❌ Model '{model}' not downloaded yet")
            print(f"     Fix: ollama pull {model}")
            return False

        resp = requests.post(
            f"{url}/api/chat",
            json={
                "model":  model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": "Reply with exactly the word: OK"},
                    {"role": "user",   "content": "test"}
                ]
            },
            timeout=30
        )
        reply = resp.json().get("message", {}).get("content", "")
        print(f"  ✅ Ollama is running — test reply: '{reply.strip()}'")
        print(f"     Model '{model}' is loaded and generating text.")
        print(f"     All auto-replies will be generated locally — no cloud AI used.")
        return True

    except requests.exceptions.ConnectionError:
        print("  ❌ Ollama is not running")
        print("     Fix: ollama serve")
        return False
    except Exception as e:
        print(f"  ❌ Ollama error: {e}")
        return False


def test_supabase():
    """
    What this checks:
      1. SUPABASE_URL and SUPABASE_SERVICE_KEY are set and valid
      2. A connection to your Supabase project can be established
      3. The 'queue' table exists (created by supabase_schema.sql)

    Why it matters:
      The Railway webhook catcher writes incoming Instagram comments to this queue.
      The local worker reads from it. Without Supabase, the two halves of the
      system can't communicate.

    If this fails:
      - Export SUPABASE_URL and SUPABASE_SERVICE_KEY in ~/.zshrc and source it
      - Make sure you ran supabase_schema.sql in the Supabase SQL editor
    """
    print("\n🗄️  Testing Supabase...")
    try:
        from supabase import create_client
        client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        client.table("queue").select("id").limit(1).execute()
        print("  ✅ Supabase connected and queue table exists")
        print("     Instagram comments from Railway will queue here.")
        print("     The worker reads from this queue every 30 seconds.")
        return True
    except Exception as e:
        print(f"  ❌ Supabase error: {e}")
        print("     Fix: export SUPABASE_URL and SUPABASE_SERVICE_KEY in ~/.zshrc")
        print("          and make sure you ran supabase_schema.sql")
        return False


def test_instagram_token():
    """
    What this checks:
      1. INSTAGRAM_ACCESS_TOKEN is set
      2. The token is valid and not expired (tokens last 60 days)
      3. Confirms which Instagram account it belongs to

    Why it matters:
      This token is what lets the worker send DMs on your behalf.
      If it's expired or invalid, every DM attempt will fail with a 190 error.

    If this fails:
      - Generate a new long-lived token — see platforms/instagram.md Step 7
      - Export the new token in ~/.zshrc and source it
    """
    print("\n📸 Testing Instagram access token...")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        print("  ❌ INSTAGRAM_ACCESS_TOKEN not set — export it in ~/.zshrc")
        return False

    try:
        resp = requests.get(
            "https://graph.instagram.com/me",
            params={"access_token": token, "fields": "id,username"},
            timeout=10
        )
        data = resp.json()

        if "error" in data:
            print(f"  ❌ Token invalid: {data['error'].get('message')}")
            print("     Fix: generate a new long-lived token — see platforms/instagram.md Step 7")
            return False

        print(f"  ✅ Token valid — account: @{data.get('username')} (id: {data.get('id')})")
        print(f"     The worker can send DMs as @{data.get('username')}.")
        print(f"     Token expires in ~60 days — refresh it at platforms/instagram.md")
        return True

    except Exception as e:
        print(f"  ❌ Instagram API error: {e}")
        return False


def test_imap():
    """
    What this checks:
      1. SMTP_USER and SMTP_PASSWORD are set
      2. Can connect to Gmail's IMAP server using those credentials
      3. Login succeeds with the Gmail App Password

    Why it matters:
      The worker fetches unread emails from Gmail via IMAP every 2 minutes.
      If IMAP login fails, no emails will be processed. Note: you need a Gmail
      App Password here — your normal Gmail password is rejected by IMAP.

    If this fails:
      - Enable IMAP in Gmail: Settings → See all settings → Forwarding and POP/IMAP
      - Make sure SMTP_PASSWORD is a Gmail App Password (not your real password)
      - Get an App Password at: myaccount.google.com/apppasswords
    """
    print("\n📥 Testing Gmail IMAP...")
    host = os.getenv("IMAP_HOST", "imap.gmail.com")
    port = int(os.getenv("IMAP_PORT", 993))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")

    if not user or not pwd:
        print("  ❌ SMTP_USER or SMTP_PASSWORD not set — export them in ~/.zshrc")
        return False

    try:
        with imaplib.IMAP4_SSL(host, port) as imap:
            imap.login(user, pwd)
        print(f"  ✅ IMAP connected as {user}")
        print(f"     The worker can fetch unread emails from your inbox.")
        print(f"     New emails will be checked every 2 minutes.")
        return True
    except imaplib.IMAP4.error as e:
        print(f"  ❌ IMAP login failed: {e}")
        print("     Fix: use a Gmail App Password — myaccount.google.com/apppasswords")
        print("          and enable IMAP in Gmail Settings")
        return False
    except Exception as e:
        print(f"  ❌ IMAP error: {e}")
        return False


def test_smtp():
    """
    What this checks:
      1. SMTP_USER and SMTP_PASSWORD are set
      2. Can connect to Gmail's SMTP server and authenticate
      3. The connection is encrypted via STARTTLS

    Why it matters:
      When the worker generates a reply to an email, it sends it via SMTP.
      If SMTP fails, email replies will never be delivered.

    If this fails:
      - Check SMTP_USER and SMTP_PASSWORD are exported in ~/.zshrc
      - Make sure SMTP_PASSWORD is a Gmail App Password (not your real password)
    """
    print("\n📤 Testing Gmail SMTP...")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", 587))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")

    if not user or not pwd:
        print("  ❌ SMTP_USER or SMTP_PASSWORD not set — export them in ~/.zshrc")
        return False

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, pwd)
        print(f"  ✅ SMTP connected as {user}")
        print(f"     The worker can send email replies from {user}.")
        print(f"     Recipients will see the reply as coming from you.")
        return True
    except smtplib.SMTPAuthenticationError:
        print("  ❌ SMTP authentication failed")
        print("     Fix: use a Gmail App Password — myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"  ❌ SMTP error: {e}")
        return False


def test_prompts():
    """
    What this checks:
      1. prompts/instagram.txt exists and is readable
      2. prompts/email.txt exists and is readable

    Why it matters:
      These files are the instructions given to Ollama — they tell the AI
      who you are, your tone, and how to write replies. Without them,
      Ollama has no context and the worker won't generate replies.

    If this fails:
      - Check that prompts/instagram.txt and prompts/email.txt exist
      - They should have been included when you cloned the project
    """
    print("\n📝 Testing prompt files...")
    from pathlib import Path
    prompts_dir = Path(__file__).parent.parent / "prompts"
    ok = True

    for platform in ["instagram", "email"]:
        f = prompts_dir / f"{platform}.txt"
        if f.exists():
            print(f"  ✅ prompts/{platform}.txt found ({len(f.read_text())} characters)")
        else:
            print(f"  ❌ prompts/{platform}.txt not found")
            ok = False

    if ok:
        print(f"     Ollama will use these instructions when generating replies.")
        print(f"     Edit them any time to change the AI's tone — no code changes needed.")

    return ok


if __name__ == "__main__":
    print("=" * 55)
    print("  local-llm-autoreply — pre-flight checks")
    print("=" * 55)
    print("\nChecking all components before starting the worker...")

    results = {
        "Ollama":          test_ollama(),
        "Supabase":        test_supabase(),
        "Instagram token": test_instagram_token(),
        "Gmail IMAP":      test_imap(),
        "Gmail SMTP":      test_smtp(),
        "Prompt files":    test_prompts(),
    }

    print("\n" + "=" * 55)
    print("  Summary:")
    all_ok = True
    for name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}")
        if not passed:
            all_ok = False

    print("=" * 55)
    if all_ok:
        print("  🚀 All checks passed — ready to run!")
        print("     Start the worker: python worker/worker.py")
        print()
        print("  What happens next:")
        print("  • Worker polls Supabase every 30s for Instagram comments")
        print("  • Worker polls Gmail every 2min for new emails")
        print("  • Ollama generates a reply for each one")
        print("  • Reply is sent as an Instagram DM or email")
    else:
        print("  ⚠️  Fix the issues above before running the worker")
        print("     Each failed check has a 'Fix:' line telling you what to do")
    print("=" * 55)
