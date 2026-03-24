---
name: local-llm-autoreply
description: |
  Helps users set up, run, and troubleshoot local-llm-autoreply — a free,
  privacy-first system that auto-replies to Instagram comments and emails using
  a local LLM (Ollama + Llama3). No cloud AI, no SaaS subscriptions, no third
  party reading messages — everything runs on the user's own machine.

  Use this skill whenever the user wants to:
  - Automate replies to Instagram comments or DMs
  - Auto-reply to emails without paying for a service
  - Replace LinkDM, Manychat, or InstantDM with a free self-hosted alternative
  - Run a local AI chatbot that responds on their behalf
  - Set up Ollama to power automated messaging
  - Keep their messages private (no OpenAI, no cloud AI)
  - Fix a broken worker, webhook, or Supabase queue
  - Add a new platform (Telegram, WhatsApp, etc.) to an existing setup

  Trigger even if the user says things like "automate my DMs", "reply to comments
  automatically", "I don't want to pay for auto-reply", "self-hosted autoresponder",
  or "private AI replies" — they almost certainly need this skill.
---

# Local LLM Auto-Reply

Auto-reply to Instagram comments and emails using Ollama + Llama3 running entirely
on the user's machine. Zero cloud AI, zero monthly fees.

---

## When this skill triggers — start here

Ask the user which situation applies:

1. **Fresh setup** — starting from scratch (most common)
2. **Something is broken** — worker won't start, no replies being sent, errors in logs
3. **Customise replies** — change the tone, persona, or reply style
4. **Add a new platform** — Telegram, WhatsApp, Twitter/X, etc.

Then jump to the relevant section below. Don't read the whole skill — just the part that matches.

---

## Fresh Setup (most common path)

Walk the user through these phases in order. Check in after each phase — don't dump everything at once.

### Phase 1 — Get the code

```bash
git clone https://github.com/thenullrabbit/local-llm-autoreply
cd local-llm-autoreply
pip install -r requirements.txt
```

Tell the user: "All credentials go in `~/.zshrc` as shell exports — we'll add them together as we go. The `.env.example` file is a reference for what's needed but is never read by the code."

---

### Phase 2 — Install and start Ollama (local AI)

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model and start
ollama pull llama3
ollama serve
```

Verify it's working:
```bash
curl http://localhost:11434/api/tags
```
Should return JSON with `llama3` in the model list. If it doesn't, don't move on — fix this first.

Add to `~/.zshrc` (these are the defaults — only needed if you change them):
```bash
export OLLAMA_URL="http://localhost:11434"
export OLLAMA_MODEL="llama3"
```

---

### Phase 3 — Create a Supabase project (free queue)

1. supabase.com → New project → choose any region → copy **Project URL** and **service_role key** (Settings → API)
2. SQL Editor → New Query → paste the contents of `supabase_schema.sql` → Run

Add to `~/.zshrc`:
```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_KEY="your-service-role-key"
```

Set the same two values on Railway (Phase 4) — both services need them.

---

### Phase 4 — Deploy the webhook catcher to Railway (free)

The webhook catcher must live in the cloud (always online) so Meta can reach it. Railway's free tier is sufficient.

```bash
npm install -g @railway/cli
railway login --browserless   # prints a URL + pairing code — open URL in any browser
railway init                  # from inside the local-llm-autoreply folder
railway service local-llm-autoreply
```

Set environment variables BEFORE deploying — the app crashes on startup without them:
```bash
railway variables set \
  SUPABASE_URL=https://your-project.supabase.co \
  SUPABASE_SERVICE_KEY=your-service-role-key \
  VERIFY_TOKEN=pick-any-random-string \
  META_APP_SECRET=your-meta-app-secret
```

Then deploy:
```bash
railway up
```

Copy the public URL Railway gives you:
```bash
railway domain
# → 🚀 https://local-llm-autoreply-production.up.railway.app
```

Verify it's live:
```bash
curl https://your-railway-url.railway.app/health
```

---

### Phase 5 — Keep Railway warm with UptimeRobot (free)

Without this, Railway goes cold after 5 minutes and the first webhook call will time out.

1. uptimerobot.com → Create free account → Add New Monitor
2. Monitor Type: HTTP(s)
3. URL: `https://your-railway-url.railway.app/ping`
4. Interval: every 5 minutes
5. Save

---

### Phase 6 — Configure platforms

Ask the user: **"Do you want Instagram, email, or both?"**

Then read the relevant platform guide and walk through it with them:
- **Instagram** → see `platforms/instagram.md`
- **Email** → see `platforms/email.md`

Quick summary of what each requires:

**Instagram** (more steps — allow 20-30 min):
- Instagram Professional account (Creator or Business)
- Facebook Page linked to Instagram
- Meta Developer app with `instagram_manage_messages` + `instagram_manage_comments`
- Long-lived access token (valid 60 days — needs manual renewal)
- Webhook registered pointing at Railway URL

**Email** (simpler — ~5 min):
- Gmail IMAP enabled (Settings → Forwarding and POP/IMAP)
- Gmail App Password from myaccount.google.com/apppasswords

Add to `~/.zshrc` after completing platform setup:

Instagram:
```bash
export INSTAGRAM_ACCESS_TOKEN="your-long-lived-token"
export INSTAGRAM_USER_ID="your-numeric-instagram-id"
export META_APP_SECRET="your-meta-app-secret"
export VERIFY_TOKEN="same-string-as-railway"
```

Email:
```bash
export SMTP_USER="your@gmail.com"
export SMTP_PASSWORD="xxxx xxxx xxxx xxxx"   # 16-char App Password — must be quoted
export YOUR_NAME="Your Name"
# Only needed if NOT using Gmail defaults:
# export IMAP_HOST="imap.gmail.com"
# export IMAP_PORT="993"
# export SMTP_HOST="smtp.gmail.com"
# export SMTP_PORT="587"
```

Then apply: `source ~/.zshrc`

---

### Phase 7 — Set fallback replies and poll intervals

Add to `~/.zshrc`:
```bash
export FALLBACK_INSTAGRAM="Hey! Thanks for your comment 👋 I'll get back to you soon."
export FALLBACK_EMAIL="Thanks for reaching out! I'll get back to you shortly."
export POLL_INTERVAL_SECONDS="30"
export EMAIL_POLL_INTERVAL_SECONDS="120"
```

Then apply: `source ~/.zshrc`

Fallbacks are sent automatically if Ollama is offline or returns nothing — the person always gets a reply.

---

### Phase 8 — Run pre-flight checks

```bash
source ~/.zshrc
python tests/test_all.py
```

This tests every configured component (Ollama, Supabase, Instagram token, Gmail IMAP) and prints pass/fail for each. Fix any failures before starting the worker. Don't skip this step.

---

### Phase 9 — Start the worker

```bash
python worker/worker.py
```

Healthy startup looks like:
```
🚀 Local worker started
✅ Ollama is running with model: llama3
⏱️  Instagram: checking Supabase every 30s
📧  Email: checking Gmail every 120s
```

If Ollama isn't running yet, the worker still starts but uses fallback replies until Ollama comes online.

**Setup is complete.** Test it: comment on one of your Instagram posts, or send yourself an email, and watch the logs.

---

## Troubleshooting

Use this when the user reports errors, no replies being sent, or the worker crashing.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Cannot connect to Ollama` | Ollama not running | `ollama serve` |
| `Model not found` | Model not pulled | `ollama pull llama3` |
| All pre-flight tests failing | Env vars not loaded | Run `source ~/.zshrc` before `python tests/test_all.py` |
| No Instagram replies | Webhook not registered | Re-register in Meta Developer dashboard |
| No Instagram replies | App in Development mode | Switch Meta app to Live mode in App Dashboard |
| Meta error 10 | Missing permission | Enable `instagram_manage_messages` in Meta app |
| Meta error 100 | Commenter > 24h ago | Nothing — Meta's rule, can't reply after 24h |
| Meta error 190 | Token expired | Generate new long-lived token (every 60 days) |
| `IMAP login error` | Wrong credentials | Use App Password, not real Gmail password |
| `IMAP not enabled` | IMAP disabled in Gmail | Gmail Settings → Forwarding and POP/IMAP → Enable |
| Email marked read but no reply sent | Bug — old code | Update to latest code; mark-as-read now happens only after successful send |
| `Invalid recipient email address` | Gmail `From` header has display name format | Update to latest code; `parseaddr()` now handles `"Name <email>"` format |
| `TypeError: unsupported operand type(s) for \|` | Python 3.9 doesn't support `str \| None` syntax | Update to latest code; `from __future__ import annotations` is now included |
| `SMTP_PASSWORD` only stores first word | Unquoted value with spaces in `~/.zshrc` | Quote it: `export SMTP_PASSWORD="xxxx xxxx xxxx xxxx"` |
| `Queue table not found` | Schema not applied | Run `supabase_schema.sql` in Supabase SQL editor |
| Railway 502 on webhook | Railway cold start | Check UptimeRobot is pinging /ping every 5 min |
| `SMTP auth failed` | App Password wrong | Regenerate at myaccount.google.com/apppasswords |

For deeper debugging, run the end-to-end test:
```bash
python tests/test_e2e.py
```

---

## Customising replies

Edit `prompts/instagram.txt` or `prompts/email.txt` — plain text, no code changes needed. Restart the worker after editing.

Tips for effective prompts:
- Tell Llama3 who the user is (their name, what they do, their tone)
- List common scenarios and how to handle each
- Set strict length limits — Instagram DMs: 1-3 sentences, email: 2-4 sentences
- End with: `Reply only with the message text — no labels, no explanation`

---

## Adding a new platform

1. Add a webhook route or poller in `webhook_catcher/app.py` or `worker/worker.py`
2. Add a sender in `senders/your_platform.py`
3. Add a prompt in `prompts/your_platform.txt`
4. Add fallback to `~/.zshrc`: `export FALLBACK_YOURPLATFORM="your default reply"`
5. Register sender in `worker/worker.py` SENDERS dict
6. Document in `platforms/your_platform.md`

---

## Running as a background service (optional)

By default the worker stops when the terminal closes. To run it automatically on boot:

**macOS (launchd):**
```bash
brew services start ollama   # auto-start Ollama on login

cat > ~/Library/LaunchAgents/com.thenullrabbit.worker.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thenullrabbit.worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/local-llm-autoreply/worker/worker.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/worker.log</string>
  <key>StandardErrorPath</key><string>/tmp/worker.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.thenullrabbit.worker.plist
tail -f /tmp/worker.log
```

**Linux (systemd):**
```bash
sudo systemctl enable ollama && sudo systemctl start ollama

sudo tee /etc/systemd/system/llm-worker.service << EOF
[Unit]
Description=Local LLM Auto-Reply Worker
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/local-llm-autoreply
ExecStart=/usr/bin/python3 /path/to/local-llm-autoreply/worker/worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable llm-worker && sudo systemctl start llm-worker
journalctl -u llm-worker -f
```

---

## Architecture reference

```
┌─────────────────────────── INTERNET ────────────────────────────┐
│                                                                  │
│  Instagram comment  ──►  webhook_catcher/app.py (Railway)        │
│                               │                                  │
│  UptimeRobot /ping  ──────────┘  keeps Railway warm              │
│                               │                                  │
│                               ▼                                  │
│                       Supabase queue table                       │
│                          (holds events)                          │
└───────────────────────────────┬─────────────────────────────────┘
                                │ polled every 30s
┌───────────────────────────────▼──────────────────────────────────┐
│                    YOUR LOCAL MACHINE                             │
│                                                                  │
│   worker/worker.py                                               │
│     ├─ process_instagram_queue()  ◄── Supabase poll              │
│     └─ process_new_emails()       ◄── Gmail IMAP (every 2 min)  │
│                 │                                                │
│                 ▼                                                │
│   worker/ollama_client.py  (Ollama on localhost:11434)           │
│                 │                                                │
│        ┌────────┴────────┐                                       │
│        ▼                 ▼                                       │
│  senders/instagram.py   senders/email.py                         │
│  (Meta Graph API v25)   (SMTP send)                              │
└──────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- Ollama runs locally — messages never sent to any cloud AI
- Supabase queue buffers Instagram events when the machine is offline
- Email uses IMAP polling — no Google Cloud or Pub/Sub required
- Railway webhook catcher is stateless (30 lines) — only queues events
- Fallback replies ensure something is always sent if Ollama is down

---

## Testing this skill

Installing the skill is safe — it only adds a markdown file to Claude Code's context. It does not touch your code, `.zshrc`, env vars, Ollama, Supabase, or anything running locally.

```bash
npx skills add thenullrabbit/local-llm-autoreply
```

Then open a **new** Claude Code session and ask:
> "I want to auto-reply to my Instagram comments for free"

The agent should trigger Phase 1 and walk through the setup. Stop before actually running any commands — just verify the instructions are correct:

- Phase 1: no `cp .env.example .env` — only `~/.zshrc` exports
- Phase 4: `railway login --browserless`, no `PORT=5000` in variables
- Phase 8: `source ~/.zshrc` before `python tests/test_all.py`
- Troubleshooting table: includes entries for env vars not loaded, Python 3.9 issue, email mark-as-read bug

To test a local (unpublished) version:
```bash
npx skills add ./   # from the project root
```

---

## Key constraints

| Constraint | Detail |
|-----------|--------|
| Instagram 24h window | Can only DM users who engaged in last 24 hours |
| Instagram rate limit | Max 200 automated DMs/hour (1.5s delay built in) |
| Token expiry | Instagram token lasts 60 days — regenerate manually |
| Machine must be on | Worker only runs when your machine is on (events queue safely) |
| Gmail App Password | Required — not your real Gmail password |
| Ollama must be running | Start with `ollama serve` before starting the worker |
