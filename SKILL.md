---
name: local-llm-autoreply
description: |
  Auto-reply to Instagram comments and emails using a local LLM (Ollama + Llama3).
  Use this skill when the user wants private, free automated replies that run entirely
  on their own machine — no cloud AI, no SaaS subscriptions, no third party reading
  their messages. Covers webhook setup, Supabase queue, local worker, and IMAP polling.
---

# Local LLM Auto-Reply Skill

Auto-reply to Instagram comments and emails using a local LLM (Ollama + Llama3).
No cloud AI, no monthly SaaS fees, no third party reading your messages.
Everything runs on your own machine.

**Platforms covered:**
- Instagram (comment → DM via Meta Graph API)
- Email (IMAP polling → SMTP reply)

**Author:** thenullrabbit  
**Tested on:** macOS, Linux  
**Requires:** Python 3.11+, Ollama, a free Supabase account, a free Railway or Render account

---

## Full Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        INTERNET (cloud)                           │
│                                                                  │
│   ┌───────────────────┐      ┌──────────────────────────────┐   │
│   │    Instagram        │      │   UptimeRobot (free)          │   │
│   │  comment trigger    │      │   pings /ping every 5 min    │   │
│   └─────────┬──────────┘      └────────────┬─────────────────┘   │
│             │                               │                    │
│             ▼                               ▼                    │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │           webhook_catcher/app.py  (Railway/Render)        │   │
│   │                                                           │   │
│   │   GET  /webhook/instagram  ← Meta verification            │   │
│   │   POST /webhook/instagram  ← incoming comment events      │   │
│   │   GET  /ping               ← UptimeRobot keep-warm        │   │
│   │   GET  /health             ← status check                 │   │
│   └─────────────────────────┬───────────────────────────────┘   │
│                              │ _queue_event()                    │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                  Supabase queue table                     │   │
│   │          supabase_schema.sql defines this table           │   │
│   │   { id, platform, sender_id, content, processed, failed } │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              ▲                                   │
│                  fetch_unprocessed() every 30s                   │
└──────────────────────────────┼───────────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────────┐
│           YOUR LOCAL MACHINE  (runs when you are online)          │
│                               │                                  │
│               ┌───────────────▼──────────────┐                  │
│               │        worker/worker.py        │                  │
│               │                               │                  │
│               │  process_instagram_queue()     │                  │
│               │  process_new_emails()          │◄─── Gmail INBOX  │
│               │  _generate_with_fallback()     │     via IMAP     │
│               └───────────────┬───────────────┘   every 2 min   │
│                               │                                  │
│                               ▼                                  │
│               ┌───────────────────────────────┐                 │
│               │     worker/ollama_client.py    │                 │
│               │                               │                 │
│               │  generate_reply(platform,      │                 │
│               │                content)        │                 │
│               │  check_ollama_health()         │                 │
│               │                               │                 │
│               │  uses prompts/instagram.txt    │                 │
│               │       prompts/email.txt        │                 │
│               │                               │                 │
│               │  ⚠ if Ollama fails →           │                 │
│               │    FALLBACK_* from .env used   │                 │
│               └───────────────┬───────────────┘                 │
│                               │                                  │
│               ┌───────────────┴───────────────┐                 │
│               ▼                               ▼                 │
│  ┌─────────────────────────┐  ┌─────────────────────────┐      │
│  │  senders/instagram.py   │  │    senders/email.py      │      │
│  │                         │  │                          │      │
│  │  send_instagram_dm()    │  │  fetch_new_emails()      │      │
│  │  Meta Graph API v25.0   │  │  send_email_reply()      │      │
│  │  POST /{id}/messages    │  │  IMAP fetch + SMTP send  │      │
│  └────────────┬────────────┘  └────────────┬────────────┘      │
└───────────────┼────────────────────────────┼────────────────────┘
                │                            │
                ▼                            ▼
       Instagram DM sent               Email reply sent
         to commenter                    to sender
```

---

## How It Works

**Instagram:**
```
Comment on post → Meta webhook → Railway catcher → Supabase queue
→ local worker polls → Ollama generates reply → DM sent via Graph API
```

**Email:**
```
Email arrives in Gmail → local worker polls IMAP every 2 min
→ fetches unread emails directly → Ollama generates reply → SMTP sends reply
```

**Why this architecture:**
- Ollama runs locally — DMs and emails never sent to any cloud AI
- Email uses IMAP polling — no Google Cloud, no Pub/Sub, no setup complexity
- Supabase queue means Instagram events are never lost when machine is offline
- Fallback replies ensure something is always sent even if Ollama is down
- UptimeRobot keeps Railway server warm — zero cold start latency

---

## Prerequisites

Before this skill can build anything, the user must manually complete:

### 1. Install Ollama
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Pull Llama3
ollama pull llama3

# Start Ollama (keep running)
ollama serve
```

### 2. Create a free Supabase project
1. Go to supabase.com → New project
2. Copy **Project URL** and **service_role key** (Settings → API)
3. SQL Editor → New Query → paste and run `supabase_schema.sql`

### 3. Deploy webhook catcher to Railway (free)
```bash
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set SUPABASE_URL=... SUPABASE_SERVICE_KEY=... VERIFY_TOKEN=... META_APP_SECRET=...
```
Copy the Railway public URL for webhook registration.

### 4. Set up UptimeRobot (free — keeps Railway warm)
1. Go to uptimerobot.com → Create free account
2. Add New Monitor:
   - Monitor Type: HTTP(s)
   - URL: `https://your-railway-url.railway.app/ping`
   - Monitoring Interval: every 5 minutes
3. Done — Railway will never cold-start again

### 5. Instagram — Meta Developer app
1. developers.facebook.com → Create App → Business type
2. Add Instagram product
3. App Settings → Basic → copy App Secret
4. Graph API Explorer → generate token with `instagram_manage_messages` + `instagram_manage_comments`
5. Exchange for long-lived token (60 days)
6. Webhooks → Instagram → Subscribe → enter Railway URL + `/webhook/instagram` + VERIFY_TOKEN
7. Subscribe to `comments` field

### 6. Email — Gmail setup
1. Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP → Save
2. Create App Password: myaccount.google.com/apppasswords
3. Add credentials to `.env`

---

## Keeping the Worker Running (Optional but Recommended)

By default, the worker runs in a terminal window. If you close the terminal or restart
your machine, it stops. Here's how to make it run automatically in the background.

### macOS — run as a background service

```bash
# Start Ollama automatically on login (do this once)
brew services start ollama

# Create a launchd service for the worker
# Replace /path/to/local-llm-autoreply with your actual project path
cat > ~/Library/LaunchAgents/com.thenullrabbit.worker.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.thenullrabbit.worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/local-llm-autoreply/worker/worker.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/worker.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/worker.log</string>
</dict>
</plist>
EOF

# Load the service
launchctl load ~/Library/LaunchAgents/com.thenullrabbit.worker.plist

# Check it is running
launchctl list | grep thenullrabbit

# View logs
tail -f /tmp/worker.log
```

### Linux — run as a systemd service

```bash
# Start Ollama automatically on boot (do this once)
sudo systemctl enable ollama
sudo systemctl start ollama

# Create a systemd service for the worker
# Replace /path/to and your-username with real values
sudo tee /etc/systemd/system/llm-worker.service << EOF
[Unit]
Description=Local LLM Auto-Reply Worker
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/local-llm-autoreply
ExecStart=/usr/bin/python3 /path/to/local-llm-autoreply/worker/worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable llm-worker
sudo systemctl start llm-worker

# Check status and view logs
sudo systemctl status llm-worker
journalctl -u llm-worker -f
```

---

## Project Structure

```
local-llm-autoreply/
├── SKILL.md
├── .env.example
├── requirements.txt
├── Procfile
├── .gitignore
├── supabase_schema.sql
├── platforms/
│   ├── instagram.md
│   └── email.md
├── prompts/
│   ├── instagram.txt
│   └── email.txt
├── webhook_catcher/
│   └── app.py
├── worker/
│   ├── worker.py
│   └── ollama_client.py
├── senders/
│   ├── instagram.py
│   └── email.py
└── tests/
    ├── test_all.py     ← run before going live
    └── test_e2e.py     ← run to test the full flow end to end
```

---

## Environment Variables

### Webhook catcher (.env on Railway)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
VERIFY_TOKEN=any-random-string
META_APP_SECRET=your-meta-app-secret
PORT=5000
```

### Local worker (.env on your machine)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
INSTAGRAM_ACCESS_TOKEN=your-long-lived-token
INSTAGRAM_USER_ID=your-instagram-numeric-id
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your-gmail-app-password
YOUR_NAME=your-name
FALLBACK_INSTAGRAM=Hey! Thanks for your comment 👋 I'll get back to you soon.
FALLBACK_EMAIL=Thanks for reaching out! I'll get back to you shortly.
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
POLL_INTERVAL_SECONDS=30
EMAIL_POLL_INTERVAL_SECONDS=120
```

---

## Running

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in your credentials

# Pre-flight checks
python tests/test_all.py

# Start worker
python worker/worker.py
```

---

## Fallback Replies

If Ollama is offline or fails to generate a reply, a safe fallback is sent automatically.
This means a reply is **always** sent — never silence.

Set fallbacks in `.env`:
```
FALLBACK_INSTAGRAM=Hey! Thanks for your comment 👋 I'll get back to you soon.
FALLBACK_EMAIL=Thanks for reaching out! I'll get back to you shortly.\n\nthenullrabbit
```

---

## Customising Replies

Edit `prompts/instagram.txt` and `prompts/email.txt`.
Plain text — no code changes needed.

Tips:
- Give Llama3 context about who you are
- List common scenarios and how to handle them
- Set strict length limits (Instagram: 1-3 sentences, Email: 2-4 sentences)
- End with: "Reply only with the message text — no labels, no explanation"

---

## Key Constraints

| Constraint | Detail |
|-----------|--------|
| Instagram 24-hour window | Can only DM users who engaged in last 24 hours |
| Instagram rate limit | Max 200 automated DMs/hour |
| Token expiry | Instagram token lasts 60 days — regenerate manually |
| Gmail IMAP | Must be enabled in Gmail settings |
| Gmail App Password | Required for IMAP/SMTP — not your real password |
| Ollama must be running | Start with `ollama serve` before running worker |
| Machine must be on | Worker only runs when your laptop is on |

---

## Common Errors

| Error | Fix |
|-------|-----|
| `Cannot connect to Ollama` | Run `ollama serve` |
| `Model not found` | Run `ollama pull llama3` |
| Meta error 10 | Enable `instagram_manage_messages` in Meta app |
| Meta error 100 | User commented more than 24 hours ago |
| Meta error 190 | Access token expired — regenerate |
| IMAP login failed | Use Gmail App Password, not real password |
| IMAP not enabled | Enable in Gmail Settings → Forwarding and POP/IMAP |
| Queue table not found | Run `supabase_schema.sql` in Supabase SQL editor |

---

## Adding More Platforms

1. Add webhook route in `webhook_catcher/app.py` (or add polling in `worker.py`)
2. Add sender in `senders/your_platform.py`
3. Add prompt in `prompts/your_platform.txt`
4. Add fallback in `.env`
5. Register sender in `worker/worker.py` SENDERS dict
6. Document in `platforms/your_platform.md`

---

## Privacy Notes

- Ollama runs entirely locally — no content sent to any external AI
- Email bodies are fetched directly via IMAP — never touch the cloud server
- Instagram comment text stored in Supabase only while queued — marked processed after reply
- Access tokens and credentials never leave your local machine
