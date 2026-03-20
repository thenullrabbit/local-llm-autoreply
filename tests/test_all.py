"""
tests/test_all.py

Run this BEFORE starting the worker to check that everything is configured correctly.
It tests each component of the system one by one and tells you exactly what to fix.

Usage:
  python tests/test_all.py

A healthy system shows all green ticks. Fix any red crosses before running the worker.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import requests
import imaplib
import smtplib


def test_ollama():
    """
    Checks that Ollama is running on your machine and that the
    correct AI model (default: llama3) has been downloaded.

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

        # Send a quick test message to confirm the model actually responds
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
    Checks that the Supabase connection works and the queue table exists.

    If this fails:
      - Check SUPABASE_URL and SUPABASE_SERVICE_KEY in your .env file
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
        return True
    except Exception as e:
        print(f"  ❌ Supabase error: {e}")
        print("     Fix: check SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        print("          and make sure you ran supabase_schema.sql")
        return False


def test_instagram_token():
    """
    Checks that your Instagram access token is valid and not expired.
    Tokens last 60 days — regenerate at developers.facebook.com when they expire.

    If this fails:
      - Generate a new long-lived token in Meta Developer → Graph API Explorer
      - Update INSTAGRAM_ACCESS_TOKEN in your .env file
    """
    print("\n📸 Testing Instagram access token...")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        print("  ❌ INSTAGRAM_ACCESS_TOKEN not set in .env")
        return False

    try:
        resp = requests.get(
            "https://graph.facebook.com/v25.0/me",
            params={"access_token": token, "fields": "id,name"},
            timeout=10
        )
        data = resp.json()

        if "error" in data:
            print(f"  ❌ Token invalid: {data['error'].get('message')}")
            print("     Fix: generate a new token at developers.facebook.com → Graph API Explorer")
            return False

        print(f"  ✅ Token valid — account: {data.get('name')} (id: {data.get('id')})")
        return True

    except Exception as e:
        print(f"  ❌ Instagram API error: {e}")
        return False


def test_imap():
    """
    Checks that we can connect to Gmail via IMAP to fetch emails.

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
        print("  ❌ SMTP_USER or SMTP_PASSWORD not set in .env")
        return False

    try:
        with imaplib.IMAP4_SSL(host, port) as imap:
            imap.login(user, pwd)
        print(f"  ✅ IMAP connected as {user}")
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
    Checks that we can connect to Gmail's SMTP server to send email replies.

    If this fails:
      - Check SMTP_USER and SMTP_PASSWORD in your .env file
      - Make sure SMTP_PASSWORD is a Gmail App Password (not your real password)
    """
    print("\n📤 Testing Gmail SMTP...")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", 587))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")

    if not user or not pwd:
        print("  ❌ SMTP_USER or SMTP_PASSWORD not set in .env")
        return False

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, pwd)
        print(f"  ✅ SMTP connected as {user}")
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
    Checks that the AI instruction files exist for each platform.
    These are the files that tell Ollama how to write replies.

    If this fails:
      - Check that prompts/instagram.txt and prompts/email.txt exist
      - They should have been included when you downloaded this project
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

    return ok


if __name__ == "__main__":
    print("=" * 55)
    print("  local-llm-autoreply — pre-flight checks")
    print("=" * 55)

    results = {
        "Ollama":         test_ollama(),
        "Supabase":       test_supabase(),
        "Instagram token":test_instagram_token(),
        "Gmail IMAP":     test_imap(),
        "Gmail SMTP":     test_smtp(),
        "Prompt files":   test_prompts(),
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
    else:
        print("  ⚠️  Fix the issues above before running the worker")
    print("=" * 55)
