"""
senders/email.py

Handles everything email-related — fetching new emails and sending replies.

Uses two standard internet protocols that have existed for decades:
  - IMAP (Internet Message Access Protocol) — for reading emails from Gmail
  - SMTP (Simple Mail Transfer Protocol) — for sending email replies

No Google Cloud account needed. No API keys. No webhooks.
Just your Gmail address and an App Password.

Important: Use a Gmail App Password, NOT your real Gmail password.
Get one at: myaccount.google.com/apppasswords
"""

import os
import imaplib
import smtplib
import email
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

IMAP_HOST     = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT     = int(os.getenv("IMAP_PORT", 993))
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # Gmail App Password — NOT your real password
YOUR_NAME     = os.getenv("YOUR_NAME", "thenullrabbit")


# ── IMAP email fetching ───────────────────────────────────────────────────────

def fetch_new_emails() -> list[dict]:
    """
    Connects to Gmail and downloads all unread emails from your INBOX.

    Works like opening your email client and checking for new messages —
    except it does it automatically in the background every 2 minutes.

    After reading each email, it marks it as 'read' in Gmail so it won't
    be fetched again on the next poll. This is the email equivalent of
    marking a Supabase row as processed.

    Prerequisites:
      - IMAP must be enabled in Gmail Settings → Forwarding and POP/IMAP
      - SMTP_PASSWORD must be a Gmail App Password (not your real password)

    Returns a list of emails, each containing:
      - uid:     Gmail's internal ID for the email
      - subject: the email subject line
      - sender:  the From address (who sent it)
      - body:    the plain text content of the email
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error("❌ SMTP_USER or SMTP_PASSWORD not set in .env")
        return []

    emails = []

    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(SMTP_USER, SMTP_PASSWORD)
            imap.select("INBOX")

            # Search for emails that haven't been read yet
            _, message_ids = imap.search(None, "UNSEEN")
            ids = message_ids[0].split()

            if not ids:
                return []

            log.info(f"📬 Found {len(ids)} new email(s)")

            for uid in ids:
                try:
                    # Download the full email
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
                    sender  = msg.get("From", "unknown")
                    body    = _extract_body(msg)

                    emails.append({
                        "uid":     uid.decode(),
                        "subject": subject,
                        "sender":  sender,
                        "body":    body
                    })

                    # Mark as read — prevents processing the same email twice
                    imap.store(uid, "+FLAGS", "\\Seen")

                except Exception as e:
                    log.error(f"❌ Failed to read email {uid}: {e}")

    except imaplib.IMAP4.error as e:
        log.error(f"❌ Gmail login failed: {e}")
        log.error("💡 Make sure IMAP is enabled in Gmail Settings → Forwarding and POP/IMAP")
        log.error("   And use a Gmail App Password: myaccount.google.com/apppasswords")
    except Exception as e:
        log.error(f"❌ Failed to fetch emails: {e}")

    return emails


# ── SMTP email sending ────────────────────────────────────────────────────────

def send_email_reply(recipient_email: str, message: str) -> bool:
    """
    Sends an email reply to the person who wrote to you.

    Uses Gmail's SMTP server to send the email from your account.
    The reply appears in the recipient's inbox as coming from you,
    with the subject line 'Re: Your message'.

    Returns True if the email was sent successfully, False otherwise.

    Note: Gmail requires an App Password for SMTP access.
    Your real Gmail password will NOT work here.
    Get an App Password at: myaccount.google.com/apppasswords
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error("❌ SMTP_USER or SMTP_PASSWORD not set in .env")
        return False

    try:
        # Build the email
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Re: Your message"
        msg["From"]    = f"{YOUR_NAME} <{SMTP_USER}>"
        msg["To"]      = recipient_email

        msg.attach(MIMEText(message, "plain"))

        # Connect to Gmail and send
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()  # Encrypts the connection for security
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipient_email, msg.as_string())

        log.info(f"✅ Email reply sent to {recipient_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error("❌ Gmail login failed for SMTP — use an App Password, not your real password")
        log.error("   Get one at: myaccount.google.com/apppasswords")
        return False
    except smtplib.SMTPException as e:
        log.error(f"❌ SMTP error: {e}")
        return False
    except Exception as e:
        log.error(f"❌ Email send error: {e}")
        return False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_body(msg) -> str:
    """
    Pulls the plain text content out of an email message.

    Emails can contain plain text, HTML, or both. We only want the
    plain text version to keep things simple and avoid sending HTML
    content to Ollama. If no plain text part is found, returns empty string.
    """
    if msg.is_multipart():
        # Email has multiple parts (e.g. plain text + HTML version)
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        # Simple single-part email
        if msg.get_content_type() == "text/plain":
            charset = msg.get_content_charset() or "utf-8"
            return msg.get_payload(decode=True).decode(charset, errors="replace")
    return ""


def _decode_header_value(value: str) -> str:
    """
    Decodes email header values that may contain special characters or
    non-English text (e.g. Japanese subject lines, accented characters).

    Email headers are sometimes encoded in formats like '=?UTF-8?B?...'
    This function converts them back to readable text.
    """
    decoded_parts = decode_header(value)
    parts = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return " ".join(parts)
