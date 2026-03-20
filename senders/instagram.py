"""
senders/instagram.py

Sends Instagram Direct Messages using Meta's official Graph API.

When the worker has a reply ready, it calls send_instagram_dm() here.
This file handles the actual HTTP request to Meta's servers that
delivers the DM to the person who left a comment.

Requirements:
  - INSTAGRAM_ACCESS_TOKEN: a long-lived token from Meta Developer dashboard
  - INSTAGRAM_USER_ID: your Instagram account's numeric ID
  Both are set in your .env file.
"""

import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
IG_USER_ID   = os.getenv("INSTAGRAM_USER_ID")

# Small pause between DMs to stay within Meta's rate limit of 200 DMs per hour.
# At 1.5 seconds per DM, we can send a maximum of 40 DMs per minute — well within limits.
DM_DELAY = 1.5


def send_instagram_dm(recipient_id: str, message: str) -> bool:
    """
    Sends a Direct Message to an Instagram user on your behalf.

    Uses Meta's Graph API — the official, approved way to send DMs
    programmatically. This is the same API used by tools like LinkDM.

    Important constraints:
      - You can only DM someone who commented on your post in the last 24 hours
      - Meta allows a maximum of 200 automated DMs per hour
      - The 1.5 second delay between sends keeps us safely within that limit

    Returns True if the DM was delivered, False if something went wrong.
    The worker logs a detailed error message if it returns False.
    """
    if not ACCESS_TOKEN or not IG_USER_ID:
        log.error("❌ INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID not set in .env")
        return False

    url = f"https://graph.facebook.com/v25.0/{IG_USER_ID}/messages"

    payload = {
        "recipient":    {"id": recipient_id},
        "message":      {"text": message},
        "access_token": ACCESS_TOKEN,
    }

    try:
        # Wait briefly before sending to respect Meta's rate limits
        time.sleep(DM_DELAY)

        response = requests.post(url, json=payload, timeout=10)
        data     = response.json()

        if response.status_code == 200 and "message_id" in data:
            log.info(f"✅ DM sent to Instagram user {recipient_id}")
            return True

        # Log a helpful error message based on Meta's error code
        error = data.get("error", {})
        _log_meta_error(error.get("code"), error.get("message", ""))
        return False

    except requests.exceptions.Timeout:
        log.error("❌ Instagram API request timed out — will retry next cycle")
        return False
    except Exception as e:
        log.error(f"❌ Unexpected error sending DM: {e}")
        return False


def _log_meta_error(code: int, message: str):
    """
    Translates Meta's numeric error codes into plain English messages
    so you can understand what went wrong without looking up the docs.

    Common codes:
      10  — your Meta app doesn't have permission to send messages
      100 — the person commented more than 24 hours ago (too late to DM)
      190 — your access token has expired (regenerate it in Meta Developer)
      368 — you've sent too many DMs too quickly (rate limit hit)
    """
    friendly_errors = {
        10:  "Permission denied — enable instagram_manage_messages in your Meta app",
        100: "Invalid recipient — the person commented more than 24 hours ago",
        190: "Access token expired — generate a new long-lived token in Meta Developer",
        368: "Rate limit hit — too many DMs sent too quickly (max 200/hour)",
    }
    friendly = friendly_errors.get(code, message)
    log.error(f"❌ Meta API error {code}: {friendly}")
