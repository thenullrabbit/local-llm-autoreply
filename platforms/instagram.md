# Platform: Instagram

Auto-reply to Instagram comments with a DM using Ollama + Meta Graph API.

---

## How It Works

1. Someone comments a trigger word (or any comment) on your Instagram post
2. Meta sends a webhook event to your Railway server
3. The event is stored in Supabase queue
4. Your local worker picks it up, sends the comment to Ollama
5. Llama3 generates a contextual reply
6. The reply is sent as a DM via Meta Graph API

---

## Prerequisites

- Instagram Professional account (Creator or Business)
- Facebook Page linked to your Instagram
- Meta Developer app with Instagram product added

---

## Step-by-Step Setup

### 1. Switch Instagram to Professional
Instagram → Settings → Account type → Switch to Professional → Creator or Business

### 2. Create a Facebook Page
facebook.com → "+" → Page → fill in name and category

### 3. Link Instagram to Facebook Page
Instagram → Settings → Accounts Centre → Connected accounts → Facebook → select your Page

### 4. Create Meta Developer App
1. Go to developers.facebook.com
2. Click "Create App" → Business type
3. Add product: Instagram
4. Go to App Settings → Basic → copy your **App Secret**

### 5. Generate a Long-Lived Access Token
1. Go to Graph API Explorer (developers.facebook.com/tools/explorer)
2. Select your app
3. Click "Generate Access Token"
4. Add permissions: `instagram_manage_messages`, `instagram_manage_comments`
5. Click Generate → copy the short-lived token
6. Exchange for long-lived token (valid 60 days):

```bash
curl -i -X GET "https://graph.facebook.com/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

### 6. Get Your Instagram User ID
```bash
curl "https://graph.facebook.com/v25.0/me?fields=id,name&access_token=YOUR_TOKEN"
```
Copy the numeric `id` — this is your `INSTAGRAM_USER_ID`.

### 7. Register the Webhook
1. Meta Developer dashboard → your app → Webhooks
2. Select "Instagram" from dropdown
3. Click "Subscribe to this object"
4. Callback URL: `https://your-railway-url.railway.app/webhook/instagram`
5. Verify token: same string as your `VERIFY_TOKEN` in `.env`
6. Click Verify and Save
7. Under "instagram" → click Subscribe next to `comments` field

### 8. Set Environment Variables
Add to your `.env` (local worker) and Railway dashboard (webhook catcher):
```
INSTAGRAM_ACCESS_TOKEN=your-long-lived-token
INSTAGRAM_USER_ID=your-numeric-id
META_APP_SECRET=your-app-secret
VERIFY_TOKEN=your-verify-token
```

---

## Testing

```bash
# Verify token is valid
curl "https://graph.facebook.com/v25.0/me?fields=id,name&access_token=YOUR_TOKEN"

# Run pre-flight checks
python tests/test_all.py

# Make a comment on your own post and watch the worker logs
python worker/worker.py
```

---

## Customising the Reply

Edit `prompts/instagram.txt` — plain text, no code changes needed.

Keep replies short: Instagram DMs should be 1-3 sentences maximum.

---

## Key Constraints

| Constraint | Detail |
|-----------|--------|
| 24-hour window | Can only DM users who engaged in last 24 hours |
| Rate limit | Max 200 automated DMs/hour |
| Token expiry | Long-lived token lasts 60 days — regenerate manually |
| Professional account | Personal accounts cannot use `instagram_manage_messages` |

---

## Common Errors

| Error code | Meaning | Fix |
|-----------|---------|-----|
| 10 | Permission denied | Enable `instagram_manage_messages` in Meta app |
| 100 | Invalid recipient | User engaged more than 24 hours ago |
| 190 | Token expired | Generate a new long-lived token |
| 368 | Rate limit | Too many DMs — worker has 1.5s delay built in |

---

## Token Refresh (every 60 days)

Run this command to get a fresh long-lived token:
```bash
curl "https://graph.facebook.com/v25.0/oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id=YOUR_APP_ID
  &client_secret=YOUR_APP_SECRET
  &fb_exchange_token=YOUR_CURRENT_TOKEN"
```
Update `INSTAGRAM_ACCESS_TOKEN` in your `.env`.
