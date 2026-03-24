# local-llm-autoreply

[![Install from skills.sh](https://img.shields.io/badge/install-skills.sh-000000)](https://skills.sh/thenullrabbit/local-llm-autoreply)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)

Auto-reply to Instagram comments and emails using a local LLM — no cloud AI, no SaaS subscriptions, no third party reading your messages.

When someone comments on your Instagram post or sends you an email, this tool automatically generates a contextual, personalised reply using **Ollama + Llama3** running entirely on your own machine and sends it back instantly.

---

## Why this exists

Every auto-reply tool on the market (LinkDM, Manychat, InstantDM) has the same problems:

- They cost $15–$99/month
- Your messages are processed on their servers
- You're locked into their UI and their rules

This project gives you the same capability for free, with full privacy, running on your own hardware. The only thing that ever touches the cloud is a tiny 30-line webhook catcher — your actual messages and AI processing stay on your machine.

---

## How it works

```
Instagram comment or incoming email
              ↓
  Webhook catcher (Railway — free, always online)
              ↓
       Supabase queue (holds events)
              ↑
   Local worker (polls when your machine is on)
              ↓
    Ollama + Llama3 (generates reply — 100% local)
              ↓
  Instagram DM or email reply sent
```

**Instagram:** Meta sends a webhook to your Railway server when someone comments → saved to Supabase → local worker picks it up → Llama3 generates a reply → DM sent via Graph API.

**Email:** Local worker polls Gmail via IMAP every 2 minutes → fetches unread emails directly → Llama3 generates a reply → SMTP sends the reply.

No email content ever touches a cloud server. No AI API calls. No subscriptions.

---

## Features

- **100% local AI** — Ollama + Llama3 runs on your machine, nothing sent to OpenAI or any other AI service
- **Instagram auto-DM** — replies to comments via Meta's official Graph API (no ToS violations)
- **Email auto-reply** — IMAP polling + SMTP, no Google Cloud or Pub/Sub needed
- **Fallback replies** — if Ollama is offline, a safe default reply is always sent
- **Resilient queue** — Supabase holds events when your machine is off, catches up when you're back
- **Always-on webhook** — UptimeRobot keeps Railway warm so no cold-start delays
- **Auto cleanup** — Supabase queue auto-deletes processed rows older than 7 days
- **Customisable prompts** — edit plain text files to change how the AI replies, no code changes needed
- **Plain English code** — every function is commented so non-developers can understand what it does

---

## Stack

| Layer | Technology | Cost |
|-------|-----------|------|
| AI model | Ollama + Llama3 (local) | Free |
| Webhook server | Flask on Railway | Free |
| Queue | Supabase Postgres | Free |
| Keep-warm | UptimeRobot | Free |
| Instagram API | Meta Graph API v25.0 | Free |
| Email | IMAP + SMTP (Gmail) | Free |

**Total cost: $0/month**

---

## Project structure

```
local-llm-autoreply/
├── SKILL.md                  ← full skill documentation for skills.sh
├── README.md                 ← you are here
├── .env.example              ← copy to .env and fill in your credentials
├── requirements.txt          ← Python dependencies
├── Procfile                  ← tells Railway how to start the webhook catcher
├── supabase_schema.sql       ← run once in Supabase SQL editor
├── platforms/
│   ├── instagram.md          ← Instagram-specific setup guide
│   └── email.md              ← Email-specific setup guide
├── prompts/
│   ├── instagram.txt         ← instructions for the AI when replying to comments
│   └── email.txt             ← instructions for the AI when replying to emails
├── webhook_catcher/
│   └── app.py                ← tiny Flask app deployed on Railway
├── worker/
│   ├── worker.py             ← main loop — runs on your local machine
│   └── ollama_client.py      ← communicates with your local Ollama instance
├── senders/
│   ├── instagram.py          ← sends DMs via Meta Graph API
│   └── email.py              ← fetches emails via IMAP, sends replies via SMTP
└── tests/
    ├── test_all.py           ← pre-flight checks before going live
    └── test_e2e.py           ← end-to-end test without needing a real comment
```

---

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) installed locally
- A free [Supabase](https://supabase.com) account
- A free [Railway](https://railway.app) account (for the webhook catcher)
- A free [UptimeRobot](https://uptimerobot.com) account (to keep Railway warm)
- An Instagram Professional account (Creator or Business)
- A Facebook Page linked to your Instagram
- A Meta Developer app with Instagram permissions

---

## Quick start

### 1. Install Ollama and pull Llama3
```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

ollama pull llama3
ollama serve
```

### 2. Clone and install dependencies
```bash
git clone https://github.com/thenullrabbit/local-llm-autoreply
cd local-llm-autoreply
pip install -r requirements.txt
```

### 3. Set up Supabase
1. Create a free project at [supabase.com](https://supabase.com)
2. Enable the pg_cron extension: **Database → Extensions → search "pg_cron" → toggle on**
3. Go to **SQL Editor → New Query** → paste `supabase_schema.sql` → **Run**
4. Copy your Project URL and service_role key from **Settings → API**

> **Note:** The "Connect to your project" dialog is for application code — ignore it here.
> You only need the SQL Editor for this step. The Project URL and service_role key come
> from Settings → API, not from the Connect dialog.

### 4. Deploy webhook catcher to Railway

Railway hosts the tiny Flask server that receives Instagram comment notifications.
It's the only piece that needs to be always online (your local machine can be off).

```bash
# Install the Railway CLI
npm install -g @railway/cli

# Log in — use --browserless if you're in a terminal without a browser
# It prints a URL and a pairing code; open the URL in any browser to confirm
railway login --browserless

# Create a new Railway project in this folder
# When prompted for a Project Name: type something like "local-llm-autoreply"
# or just press Enter to accept the randomly generated name
railway init

# Set environment variables BEFORE deploying — the app crashes on startup without them
# Replace the values with your real credentials from the earlier steps
#
# Where to find each value:
#   SUPABASE_URL         → Supabase dashboard → Settings → API Keys → Project URL
#   SUPABASE_SERVICE_KEY → Supabase dashboard → Settings → API Keys → Legacy tab → service_role key (starts with eyJ...)
#   VERIFY_TOKEN         → make up any string (e.g. mynullrabbittoken) — you'll enter this same string in Meta Developer later
#   META_APP_SECRET      → Meta Developer dashboard → your app → App Settings → Basic → App Secret (set this later)
#
# Alternatively, set variables via the Railway web dashboard:
#   railway.app → your project → click the service → Variables tab → + New Variable
railway variables set \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_SERVICE_KEY=your-service-role-key \
  VERIFY_TOKEN=your-chosen-token \
  META_APP_SECRET=your-meta-app-secret

# Deploy the webhook_catcher/app.py to Railway
# This uploads your code and starts the Flask server
# Railway already has the env vars so it will boot cleanly
railway up
```

**How `railway up` knows what to run:**
`railway up` uploads the entire project folder. Railway then reads the `Procfile`
at the project root to find the start command:

```
web: gunicorn webhook_catcher.app:app --bind 0.0.0.0:$PORT
```

- `webhook_catcher.app` = the `webhook_catcher/` folder → `app.py` file
- `:app` = the Flask object named `app` inside that file
- `$PORT` = automatically assigned by Railway
- `worker/worker.py` is intentionally absent — it runs on your local machine only, not Railway

After `railway up` finishes, Railway auto-generates a public domain. Retrieve it with:

```bash
railway domain
# → 🚀 https://local-llm-autoreply-production.up.railway.app
```

You can also find it in the Railway dashboard:
**service → Settings tab → Networking section → Public Networking**
(the domain is already generated — no button to click, just copy it from there)

Save this URL — you'll need it in the next two steps:

| Purpose | URL |
|---|---|
| UptimeRobot keep-warm monitor | `https://your-url.railway.app/ping` |
| Meta webhook registration | `https://your-url.railway.app/webhook/instagram` |

**Verify your server is working** by opening both URLs in a browser:
- `/ping` → should return `{"message":"pong","status":"ok"}` ✅
- `/webhook/instagram` → should return `Forbidden` ✅ (correct — it rejects browser visits,
  it only accepts signed POST requests from Meta. This is not an error.)

### 5. Set up UptimeRobot

**Why this is needed:** Railway's free tier shuts your server down after ~10 minutes of no
traffic. When Instagram sends a comment event to a sleeping server, Railway has to wake it
up first (cold-start delay), and Instagram may give up before it responds. UptimeRobot pings
your server every 5 minutes to keep it permanently awake — for free.

1. Create a free account at [uptimerobot.com](https://uptimerobot.com)
2. Click **Add New Monitor** and fill in:
   - Monitor Type: **HTTP(s)**
   - Friendly Name: `local-llm-autoreply`
   - URL: your Railway URL from the previous step + `/ping`
     e.g. `https://local-llm-autoreply-production.up.railway.app/ping`
   - Monitoring Interval: **5 minutes**
3. Click **Create Monitor**

> If you upgrade Railway to a paid plan, you can skip this step — paid plans don't sleep.

### 6. Configure credentials

```bash
cp .env.example .env
```

Fill in the non-sensitive values directly in `.env` (Supabase URL, model name, your name, etc.).

**For sensitive credentials (Gmail App Password, tokens), use shell environment variables
instead of writing them in any file.** Add these to your `~/.zshrc`:

```bash
export SMTP_USER="your@gmail.com"
export SMTP_PASSWORD="your-gmail-app-password"   # App Password from myaccount.google.com/apppasswords
export SUPABASE_SERVICE_KEY="eyJ..."
export INSTAGRAM_ACCESS_TOKEN="..."
```

Then apply it:
```bash
source ~/.zshrc
```

`os.getenv()` reads shell environment variables with the same priority as `.env` — the worker
will pick them up automatically. Shell exports live in your home directory and are never
part of the project, so there's no risk of accidentally committing them.

The `.env` file is already in `.gitignore` so it won't be pushed to GitHub either way,
but keeping secrets in `~/.zshrc` is the cleaner approach.

**Where to get each credential:**

| Credential | Guide |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`, `META_APP_SECRET` | → [platforms/instagram.md](platforms/instagram.md) |
| `SMTP_PASSWORD` (Gmail App Password) | → [platforms/email.md](platforms/email.md) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | → Supabase dashboard → Settings → API Keys |

### 7. Run pre-flight checks
```bash
python tests/test_all.py
```

### 8. Start the worker
```bash
python worker/worker.py
```

---

## Customising replies

Edit the plain text files in `prompts/` — no code changes needed:

- `prompts/instagram.txt` — controls how the AI replies to Instagram comments
- `prompts/email.txt` — controls how the AI replies to emails

Restart the worker after editing.

---

## Running as a background service

See [SKILL.md](SKILL.md) for full instructions on running the worker automatically on boot using `launchd` (macOS) or `systemd` (Linux).

---

## Platform setup guides

Detailed step-by-step setup for each platform:

- [Instagram setup](platforms/instagram.md)
- [Email setup](platforms/email.md)

---

## Testing

```bash
# Check all components are configured correctly
python tests/test_all.py

# Test the full pipeline end to end (worker must be running)
python tests/test_e2e.py
```

---

## This project as a skill

This project is also published as a reusable skill on [skills.sh](https://skills.sh) — meaning any AI coding agent (Claude Code, Cursor, Copilot etc.) can install it with one command and build this for you automatically:

```bash
npx skills add thenullrabbit/local-llm-autoreply
```

See [SKILL.md](SKILL.md) for the full skill documentation.

---

## Limitations

- The worker only runs when your machine is on — events queue up safely in Supabase until you're back online
- Instagram: can only DM users who engaged in the last 24 hours (Meta's rule)
- Instagram: max 200 automated DMs per hour (built-in 1.5s delay handles this)
- Instagram access token expires every 60 days — regenerate manually
- Gmail App Password required — not your real Gmail password

---

## Contributing

Found a bug or want to add a new platform? PRs welcome.

To add a new platform:
1. Add a webhook route or poller in `webhook_catcher/app.py` or `worker/worker.py`
2. Add a sender in `senders/your_platform.py`
3. Add a prompt in `prompts/your_platform.txt`
4. Document it in `platforms/your_platform.md`
5. Update `SKILL.md`

---

## License

MIT — do whatever you want with it.

---

Built by [thenullrabbit](https://thenullrabbit.com) 
