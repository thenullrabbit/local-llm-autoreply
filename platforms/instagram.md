# Platform: Instagram

Auto-reply to Instagram comments with a DM using Ollama + Meta Graph API.

---

## How It Works

1. Someone comments on your Instagram post
2. Meta sends a webhook event to your Railway server
3. The event is stored in Supabase queue
4. Your local worker picks it up, sends the comment to Ollama
5. Llama3 generates a contextual reply
6. The reply is sent as a DM via Meta Graph API

---

## What You Need to Set Up (Account Overview)

This project involves four separate Meta entities. All four must exist and be connected:

```
Instagram account (Professional)
        ↓ linked to
Facebook Page
        ↓ linked to (optional but common)
Meta Business Portfolio
        ↓ used by
Meta Developer App  ←── this is where the API access lives
```

**Instagram account** — must be Professional (Creator or Business). Personal accounts cannot send DMs via API.

**Facebook Page** — required for receiving webhook events (comment notifications). Not needed for token generation or DM sending in the new Instagram Business Login flow, but still needed for the webhook subscription.

**Meta Business Portfolio** — if your Facebook Page is managed through a Business Portfolio (Meta Business Suite), this affects how you access the Page via API. `me/accounts` returns empty in this case — see the gotchas section.

**Meta Developer App** — the app you create at developers.facebook.com. It holds your Instagram product, your API credentials, and your webhook configuration.

---

## Why a Facebook Page is Required

The Facebook Page is required specifically for **webhook subscriptions** (receiving comment notifications). Meta's comment webhook system is tied to Pages.

For **token generation** and **sending DMs**, the new Instagram Business Login flow connects to your Instagram account directly — the Facebook Page is not involved in those steps.

Without a Facebook Page:
- ❌ You cannot receive comment webhook events
- ❌ The webhook subscription step will fail

You are not required to post anything on Facebook or maintain a Facebook audience. The Page exists purely as a connector for Meta's webhook system.

---

## Step-by-Step Setup

### 1. Switch Instagram to Professional

Instagram app → **Settings → Account type → Switch to Professional** → choose Creator or Business.

### 2. Create a Facebook Page

Go to [facebook.com](https://facebook.com) → click **"+"** → **Page** → fill in a name and category. The name and category don't matter — it's a technical connector, not a public presence.

### 3. Link Instagram to Facebook Page

> ⚠️ Do NOT use Accounts Center for this. Connecting via Accounts Center links profiles, not Pages, and does not enable webhook access.

Correct method:
1. Go to your Facebook Page → **Settings → Linked accounts** (or "Instagram")
2. Click **Connect Instagram account**
3. Log in with your Instagram credentials and approve
4. Confirm: Page → Settings → you should see your Instagram account listed

> ⚠️ If your Facebook Page is managed through a **Meta Business Portfolio** (Meta Business Suite), `me/accounts` will return an empty list when queried via the Graph API. This is normal — your Page is owned by the portfolio, not directly by your personal account. You can still complete the setup below without needing to query the Page via API.

### 4. Create a Meta Developer App

> ⚠️ Meta redesigned their developer portal in 2025. The standard "Create App" flow shows 13 use cases — none of them lead to Instagram messaging. Follow the exact path below.

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **"Create App"**
3. On the **"What do you want your app to do?"** screen, scroll to the very bottom
4. Select **"Other (This option is going away soon)"** — this is the only option that exposes Instagram API access
5. On the next screen, select **Business** as the app type
6. Give your app a name (e.g. `yourname-autoreply-bot-IG`) → click **Create App**
7. You land on **"Add products to your app"** — click **Set up** next to **Instagram**
8. You are now on the **"API setup with Instagram Business Login"** page

Note two values from this page:
- **Instagram app ID** — shown in the middle column
- **Instagram app secret** — click **Show** next to it and copy the value → this is your `META_APP_SECRET`

### 5. Add Your Instagram Account as a Tester

> ⚠️ You must do this before generating tokens. Skipping it causes "Insufficient Developer Role" when you try to connect your account.

1. In your app dashboard, go to **App Roles → Roles**
2. Scroll down to **Instagram Testers**
3. Click **Add Instagram Testers** → type your Instagram username → **Submit**
4. On your phone: Instagram app → **Settings → Apps and websites → Tester Invites** → **Accept**

### 6. Configure OAuth Redirect URI

On the "API setup with Instagram Business Login" page, scroll to section **3 "Set up Instagram business login"** → click **Set up** → add `https://localhost/` as an OAuth redirect URI → **Save**.

This is required for the token generation step below.

### 7. Generate a Long-Lived Access Token

> ⚠️ The "Generate token" button on the dashboard creates an implicit token that **cannot** be exchanged for a long-lived token, and caches the old token on repeat clicks. You must use the OAuth authorization code flow below.

**Step 1 — Visit the authorization URL in your browser** (replace `YOUR_INSTAGRAM_APP_ID`):

```
https://api.instagram.com/oauth/authorize?client_id=YOUR_INSTAGRAM_APP_ID&redirect_uri=https://localhost/&scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments&response_type=code
```

Log in and approve the permissions. You'll be redirected to `https://localhost/?code=XXXXXXXX#_`.

The page will show **"This site can't be reached"** — that is **expected**. Copy the `code=` value from the URL bar (everything between `code=` and `#_`).

**Step 2 — Exchange code for short-lived token:**

```bash
curl -X POST "https://api.instagram.com/oauth/access_token" \
  -d "client_id=YOUR_INSTAGRAM_APP_ID" \
  -d "client_secret=YOUR_INSTAGRAM_APP_SECRET" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=https://localhost/" \
  -d "code=YOUR_CODE_FROM_URL"
```

**Step 3 — Exchange for long-lived token immediately** (short-lived tokens expire in ~1 hour):

```bash
curl "https://graph.instagram.com/access_token?grant_type=ig_exchange_token&client_secret=YOUR_INSTAGRAM_APP_SECRET&access_token=YOUR_SHORT_LIVED_TOKEN"
```

Copy the returned `access_token` → this is your `INSTAGRAM_ACCESS_TOKEN`. Valid for 60 days.

### 8. Get Your Instagram User ID

```bash
curl "https://graph.instagram.com/me?fields=id,username&access_token=YOUR_LONG_LIVED_TOKEN"
```

Copy the numeric `id` → this is your `INSTAGRAM_USER_ID`.

### 9. Register the Webhook

> ⚠️ **Switch your app to Live mode first.** Meta only delivers webhooks to apps in Live mode. In Development mode the webhook form will show a validation error: "To receive webhooks, app mode should be set to 'Live'".
>
> To switch: in your app dashboard, look for the **"App Mode"** toggle (top of the left sidebar or top bar). Click it and switch from **Development** to **Live**.

1. In your Meta Developer app dashboard, go to **Instagram → API setup with Instagram Business Login**
2. Scroll to section **2 "Configure webhooks"** → click **Set up**
3. Enter:
   - **Callback URL**: `https://your-railway-url.railway.app/webhook/instagram`
   - **Verify token**: the same string you set as `VERIFY_TOKEN` on Railway (and in your `~/.zshrc`)
4. Click **Verify and Save**
   - Meta will send a GET request to your Railway URL to verify it. If it fails, check that Railway is deployed and the `VERIFY_TOKEN` variable on Railway matches exactly.
5. Under the webhook fields list, subscribe to **`comments`**

### 10. Set Environment Variables

These must be set in two places:

**Local machine** — add to `~/.zshrc` and run `source ~/.zshrc`:
```bash
export INSTAGRAM_ACCESS_TOKEN="your-long-lived-token"
export INSTAGRAM_USER_ID="your-numeric-id"
export META_APP_SECRET="your-instagram-app-secret"
export VERIFY_TOKEN="your-verify-token"
```

**Railway** — already set in Step 4, but confirm all four are present:
```bash
railway service local-llm-autoreply
railway variables
```

---

## Testing

```bash
# Verify token is valid
curl "https://graph.instagram.com/me?fields=id,username&access_token=YOUR_TOKEN"

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
| Token expiry | Long-lived token lasts 60 days — refresh before it expires |
| Professional account | Personal accounts cannot use the messaging API |

---

## Common Gotchas

| Symptom | Cause | Fix |
|---------|-------|-----|
| No Instagram option when creating app | Meta hid it — standard "Create App" flow shows 13 unrelated use cases | Scroll to bottom of use cases → select "Other (going away soon)" |
| "Insufficient Developer Role" when adding account | Instagram account not added as Tester first | App Roles → Instagram Testers → add username → accept invite in Instagram app |
| Token exchange returns "Session key invalid" (code 452) | Token was generated via the "Generate token" button (implicit flow — not exchangeable) | Use the full OAuth code flow in Step 7 |
| "Generate token" button shows old cached token | Button does not regenerate — it shows the last token | Use the OAuth URL approach in Step 7 instead |
| `me/accounts` returns empty list | Your Facebook Page is owned by a Meta Business Portfolio, not your personal account directly | Normal — you don't need to query the Page for this project's setup |
| Webhook form shows "app mode should be set to 'Live'" | Meta app is still in Development mode | Toggle app to Live mode (top of app dashboard sidebar) before registering the webhook |
| Webhook events not arriving | App in Development mode, or webhook not subscribed to `comments`, or Instagram not linked to Facebook Page | Switch app to Live, re-check Step 3 (Page link) and Step 9 (webhook subscription) |

---

## Common Errors

| Error code | Meaning | Fix |
|-----------|---------|-----|
| 10 | Permission denied | Check `instagram_business_manage_messages` is in your token's scopes |
| 100 | Invalid recipient | User commented more than 24 hours ago |
| 190 | Token expired | Refresh or regenerate the long-lived token |
| 368 | Rate limit | Too many DMs — worker has 1.5s delay built in |
| 452 | Session key invalid | Token from implicit flow — use OAuth code flow in Step 7 |

---

## Token Refresh (every 60 days)

**If your token has not yet expired**, refresh it with one command:

```bash
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=YOUR_CURRENT_LONG_LIVED_TOKEN"
```

This resets the 60-day expiry from today. Update `INSTAGRAM_ACCESS_TOKEN` in `~/.zshrc` and run `source ~/.zshrc`.

**If your token has already expired**, go through Steps 1–3 of Step 7 again to get a new one.
