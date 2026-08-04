# Production setup — real accounts, Shopify, Gmail

## 1. Backend environment

Copy `backend/.env.example` to `backend/.env` and fill in all values.

```powershell
cd backend
py -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## 2. Email verification (your first real account)

Configure SMTP (Gmail example: use an [App Password](https://support.google.com/accounts/answer/185833)):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
SMTP_FROM=you@gmail.com
```

**Without SMTP:** in `DEBUG=true`, the 6-digit code is printed in the **backend terminal** when you register.

1. Open http://localhost:5173/register  
2. Create your account  
3. Enter the code at `/verify-email`  
4. You are logged in with a real DB user (SQLite file: `backend/data/app_manager.db`)

## 3. Shopify store + webhooks

1. [Shopify Partners](https://partners.shopify.com) → Apps → Create app  
2. Set **App URL** to your public backend URL (see below)  
3. **Allowed redirection URL(s):**  
   `https://YOUR_PUBLIC_URL/api/v1/stores/shopify/callback`  
4. Copy Client ID and Secret to `.env`:

```env
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
APP_URL=https://YOUR_PUBLIC_URL
```

### Local development (required for OAuth + webhooks)

Shopify must reach your machine. Use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Set `APP_URL=https://abc123.ngrok-free.app` in `.env`, restart the API, and use that URL in the Shopify app settings.

Webhooks are registered automatically to:

`{APP_URL}/api/v1/webhooks/shopify`

Topics: `app/uninstalled`, `orders/create`, `orders/paid`, fulfillments, etc. (see `webhook_topics.py`)

In the app: **Settings → Stores → Connect store** → enter `your-store.myshopify.com`

## 3b. Meta Conversions API (server-side Purchase tracking)

Forwards Shopify paid orders to Meta CAPI so purchases still count when the browser Pixel is blocked.

1. Open **Apps → Server-Side Tracking**
2. Enter **Meta Pixel ID**
3. Paste a **Conversions API access token** (Events Manager → Data sources → your Pixel → Settings → Generate access token), or enable fallback to the Analytics/Ads Marketing API token
4. Set **event_id scheme** to match your storefront Pixel Purchase `eventID` (default: Shopify order id)
5. Optionally set a **Test event code** from Events Manager → Test Events
6. Enable and save → place a test order → confirm the event in Meta Test Events (should show **Deduplicated** if Pixel + CAPI share the same `event_id`)

Webhook path (already HMAC-verified): `{APP_URL}/api/v1/webhooks/shopify`

Stats API (auth required): `GET /api/v1/meta-capi/stores/{store_id}/stats`

**Theme (required for best match quality):** publish the PHX theme updates (`meta-capi-attribution` snippet/JS), then in Theme settings → **Meta CAPI (App Manager)** paste the browser event token from Server-Side Tracking settings. This captures `fbp`/`fbc`/`fbclid`, sends ViewContent/AddToCart, and passes IDs into Phoenix checkout. See `docs/META_CAPI.md`.

Reconnect the store (or re-register webhooks) so `checkouts/create` is subscribed for InitiateCheckout.

## 4. Gmail connection & Google sign-in

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs → enable **Gmail API**  
2. OAuth consent screen (External) → add test users  
3. Credentials → OAuth client (Web) — add **both** redirect URIs:

   - `http://127.0.0.1:8000/api/v1/gmail/oauth/callback` — connect Gmail in Settings  
   - `http://127.0.0.1:8000/api/v1/auth/google/callback` — Continue with Google (sign up / sign in)  
     (or your ngrok URL + the same paths)

```env
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
```

In the app:
- **Login / Register** → **Continue with Google** (creates or signs in a verified account)
- **Settings → Gmail → Connect Gmail** (link a mailbox for sending)

## 5. Security checklist for production

- Set strong `JWT_SECRET_KEY` and `ENCRYPTION_KEY`  
- Use PostgreSQL: `DATABASE_URL=postgresql://user:pass@host/db`  
- Set `DEBUG=false`  
- Serve over HTTPS only  
- Never commit `.env`
