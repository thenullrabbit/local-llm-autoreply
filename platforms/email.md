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
Marks them as read (so they aren't processed again)
        ↓
Sends each email body to Ollama
        ↓
Llama3 generates a contextual reply
        ↓
SMTP sends the reply
```

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
- A Gmail App Password

---

## Step-by-Step Setup

### 1. Enable IMAP in Gmail
1. Go to Gmail → Settings (gear icon) → See all settings
2. Click "Forwarding and POP/IMAP" tab
3. Under IMAP Access → select "Enable IMAP"
4. Save Changes

### 2. Create a Gmail App Password
Gmail requires an App Password for IMAP/SMTP access (not your real password):
1. Go to myaccount.google.com/apppasswords
2. You may need to enable 2-Step Verification first
3. Select app: Mail, device: your computer
4. Click Generate → copy the 16-character password
5. This goes in `SMTP_PASSWORD` in your `.env`

### 3. Set Environment Variables
```bash
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-16-char-app-password
YOUR_NAME=thenullrabbit
EMAIL_POLL_INTERVAL_SECONDS=120
```

---

## Testing

```bash
# Run pre-flight checks
python tests/test_all.py

# Send yourself a test email and watch the worker logs
python worker/worker.py
```

---

## Customising the Reply

Edit `prompts/email.txt` — plain text, no code changes needed.
Email replies should be 2-4 sentences, warm but professional.

---

## Fallback Reply

If Ollama is offline or fails, a safe default reply is sent automatically.
Set it in `.env`:
```
FALLBACK_EMAIL=Thanks for reaching out! I'll get back to you shortly.\n\nthenullrabbit
```

---

## Key Constraints

| Constraint | Detail |
|-----------|--------|
| IMAP must be enabled | Off by default in Gmail — enable in Settings |
| App Password required | Gmail requires App Password for IMAP/SMTP |
| Poll interval | Default 2 minutes — adjust `EMAIL_POLL_INTERVAL_SECONDS` |
| Marks as read | Fetched emails are marked read so they aren't processed twice |
| Machine must be on | IMAP polling only runs when your laptop is running the worker |

---

## Common Errors

| Error | Fix |
|-------|-----|
| `IMAP login error` | Check SMTP_USER and SMTP_PASSWORD in .env |
| `IMAP4.error: LOGIN failed` | Use App Password, not your real Gmail password |
| `IMAP not enabled` | Enable IMAP in Gmail Settings → Forwarding and POP/IMAP |
| `SMTP auth failed` | App Password incorrect — regenerate at myaccount.google.com/apppasswords |
| Emails not being fetched | Check IMAP is enabled and App Password is correct |
