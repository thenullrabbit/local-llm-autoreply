# Platform: Email

Auto-reply to incoming emails using Ollama + IMAP polling + SMTP.
No webhooks, no Google Cloud, no Pub/Sub — everything runs locally.

---

## How It Works

```
New email arrives in Gmail INBOX
        ↓
Local worker polls IMAP every 2 minutes
        ↓
Fetches unread emails directly from Gmail
        ↓
Sends each email's subject + body to Ollama
        ↓
Llama3 generates a contextual reply
        ↓
SMTP sends the reply back to the sender
        ↓
Email is marked as read (only after successful send)
```

**Why mark-as-read happens last:**
The email is only marked as read *after* the reply is confirmed sent.
If anything fails along the way (Ollama down, SMTP error, etc.), the email
stays unread and will be retried automatically on the next 2-minute poll.
Nothing is silently lost.

**Why IMAP polling instead of webhooks:**
- No Google Cloud project needed
- No Pub/Sub setup
- No verified domain required
- Everything stays on your local machine
- Simple, reliable, zero overhead

---

## Prerequisites

- A Gmail account
- IMAP enabled in Gmail settings
- A Gmail App Password (not your real password)

---

## Step-by-Step Setup

### 1. Enable IMAP in Gmail
1. Go to Gmail → Settings (gear icon) → See all settings
2. Click the "Forwarding and POP/IMAP" tab
3. Under IMAP Access → select "Enable IMAP"
4. Save Changes

### 2. Create a Gmail App Password

Gmail requires an App Password for IMAP/SMTP access — your real Gmail
password won't work here, and it shouldn't be used.

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You may need to enable 2-Step Verification first
3. Click "Create" → give it any name (e.g. "local-llm-autoreply")
4. Google generates a 16-character password — copy it immediately
5. You won't see it again, so paste it somewhere safe

### 3. Set Environment Variables

Add to `~/.zshrc` and run `source ~/.zshrc`:

```bash
export SMTP_USER="your@gmail.com"
export SMTP_PASSWORD="xxxx xxxx xxxx xxxx"   # the 16-char App Password from step 2
export YOUR_NAME="thenullrabbit"              # how your name appears in replies
```

The IMAP/SMTP hosts and ports default to Gmail's standard values — you only
need to set them if you're using a different email provider:

```bash
export IMAP_HOST="imap.gmail.com"   # default — no need to set for Gmail
export IMAP_PORT="993"              # default
export SMTP_HOST="smtp.gmail.com"   # default
export SMTP_PORT="587"              # default
```

---

## Testing

```bash
# Verify IMAP and SMTP connections are working
source ~/.zshrc
python tests/test_all.py

# Send a test email to your SMTP_USER address, then run the full pipeline test:
python tests/test_e2e.py

# Or start the worker and send yourself an email — watch the terminal
python worker/worker.py
```

---

## Customising the Reply

Edit `prompts/email.txt` — plain text, no code changes needed.
Email replies should be 2-4 sentences, warm but professional.

Restart the worker after editing.

---

## Fallback Reply

If Ollama is offline or fails, a safe default reply is sent automatically.
Customise it by exporting in `~/.zshrc`:

```bash
export FALLBACK_EMAIL="Thanks for reaching out! I'll get back to you shortly.\n\nthenullrabbit"
```

---

## Key Constraints

| Constraint | Detail |
|-----------|--------|
| IMAP must be enabled | Off by default in Gmail — enable in Settings → Forwarding and POP/IMAP |
| App Password required | Gmail blocks regular passwords for IMAP/SMTP — App Password only |
| Poll interval | Default 2 minutes — adjust with `EMAIL_POLL_INTERVAL_SECONDS` env var |
| Mark-as-read order | Emails are marked read **after** a successful reply, not during fetch |
| Retry on failure | If reply fails, email stays unread and is retried next poll |
| Machine must be on | IMAP polling only runs while your laptop is running the worker |
| Body truncated | Incoming bodies capped at 8000 chars before going to Ollama |
| Reply truncated | Outgoing replies capped at 4000 chars |

---

## Common Errors

| Error | Fix |
|-------|-----|
| `IMAP login error` | Check SMTP_USER and SMTP_PASSWORD are exported in ~/.zshrc |
| `IMAP4.error: LOGIN failed` | Use App Password, not your real Gmail password |
| `IMAP not enabled` | Enable IMAP in Gmail Settings → Forwarding and POP/IMAP |
| `SMTP auth failed` | App Password incorrect — regenerate at myaccount.google.com/apppasswords |
| Emails not being fetched | Check IMAP is enabled and credentials are sourced (`source ~/.zshrc`) |
| Email marked read but no reply | Old bug (fixed) — update to latest code and re-run |
