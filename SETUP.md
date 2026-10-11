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

1. [Dev Dashboard](https://dev.shopify.com) → create the app in your **Partner organization**  
2. Paste its Client ID into `shopify.app.toml` and run `shopify app deploy`. That pushes:
   - **App URL:** `https://YOUR_PUBLIC_URL/api/v1/stores/shopify/launch`
   - **Allowed redirection URL:** `https://YOUR_PUBLIC_URL/api/v1/stores/shopify/callback`
   - **Embedded:** off, plus the access scopes  
3. Copy Client ID, Secret, and the install link (Distribution card) to `.env`:

```env
SHOPIFY_CLIENT_ID=...
SHOPIFY_CLIENT_SECRET=...
SHOPIFY_INSTALL_URL=https://admin.shopify.com/oauth/install_custom_app?...
APP_URL=https://YOUR_PUBLIC_URL
```

Installs always start from Shopify (install link, App Store listing, or Apps in the Shopify
admin). Shopify opens the App URL, App Manager goes straight to OAuth, and the merchant lands on
**Settings → Stores**. If they are not signed in to App Manager yet, they sign in or register and
the store is attached automatically.

### Local development (required for OAuth + webhooks)

Shopify must reach your machine. Use [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Set `APP_URL=https://abc123.ngrok-free.app` in `.env`, restart the API, and use that URL in the Shopify app settings.

Webhooks are registered automatically to:

`{APP_URL}/api/v1/webhooks/shopify`

Topics: `app/uninstalled`, `orders/create`, `orders/paid`, fulfillments, etc. (see `webhook_topics.py`)

Mandatory compliance webhooks (`customers/data_request`, `customers/redact`, `shop/redact`) use the
same URL. They are declared in `shopify.app.toml`, so `shopify app deploy` subscribes them.

In the app: **Settings → Stores → Connect store → Install from Shopify** (uses `SHOPIFY_INSTALL_URL`).
Existing stores that need new permissions use **Reconnect**.

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

   - `http://127.0.0.1:8001/api/v1/gmail/oauth/callback` — connect Gmail in Settings  
   - `http://127.0.0.1:8001/api/v1/auth/google/callback` — Continue with Google (sign up / sign in)  
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

## 6. Production VPS (nginx + systemd)

This VPS hosts **two sites**. Treat them as separate nginx files:

| Domain | nginx file | Touch it? |
|---|---|---|
| `d4technology.ca` | whatever is already in `sites-enabled` for that domain | **No — leave it** |
| `appmanager.store` | `/etc/nginx/sites-available/appmanager.store` | Yes, this one only |

App Manager needs its **own** `server_name appmanager.store` blocks on ports 80 and 443. If the 443 block is missing, browsers get the `d4technology.ca` certificate and HTTPS looks down. That does **not** mean d4technology is broken.

Repo files:

- `deploy/nginx-appmanager.store.conf`
- `deploy/appmanager.service`

### Do not

- Edit the d4technology.ca site file
- Add `default_server` to App Manager
- Run `certbot --nginx` with no `-d` (that can rewrite other sites)
- Put App Manager `location` / `ssl_certificate` lines inside the d4technology server block

### API process

```bash
sudo cp /var/www/appmanager/deploy/appmanager.service /etc/systemd/system/appmanager.service
sudo systemctl daemon-reload
sudo systemctl enable --now appmanager
curl -s http://127.0.0.1:8001/health
# must print: {"status":"ok","app":"App Manager"}
```

`.env` belongs at `/var/www/appmanager/backend/.env` (not in git).

### nginx — App Manager file only

```bash
# Confirm d4technology is its own file (do not change these)
ls -l /etc/nginx/sites-enabled/

sudo cp /var/www/appmanager/deploy/nginx-appmanager.store.conf /etc/nginx/sites-available/appmanager.store
sudo ln -sf /etc/nginx/sites-available/appmanager.store /etc/nginx/sites-enabled/appmanager.store

# If appmanager lines were pasted into the d4technology file, remove them from THAT file.
grep -n "appmanager" /etc/nginx/sites-enabled/*

# Cert for this domain only — certonly does not rewrite d4technology.ca
sudo certbot certonly --nginx -d appmanager.store -d www.appmanager.store

sudo nginx -t && sudo systemctl reload nginx
```

`proxy_pass` must be `http://127.0.0.1:8001` with **no trailing slash**. A trailing slash strips `/api` and causes Google login JSON errors and `Method Not Allowed` on password login.

### Checks

```bash
curl -sI https://d4technology.ca/ | head
curl -s http://127.0.0.1:8001/health
curl -sI https://appmanager.store/ | head
curl -s https://appmanager.store/health
curl -s https://appmanager.store/api/v1/auth/google/authorize
```

`d4technology.ca` should still be 200. App Manager `/health` and `/api/...` must return JSON, not HTML. The HTTPS cert for `appmanager.store` must be for that hostname, not `d4technology.ca`.
