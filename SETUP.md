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

Topics: `app/uninstalled`, `orders/create`

In the app: **Settings → Stores → Connect store** → enter `your-store.myshopify.com`

## 4. Gmail connection

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs → enable **Gmail API**  
2. OAuth consent screen (External) → add test users  
3. Credentials → OAuth client (Web):

   - Redirect URI: `http://127.0.0.1:8000/api/v1/gmail/oauth/callback`  
     (or your ngrok URL + same path)

```env
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
```

In the app: **Settings → Gmail → Connect Gmail**

## 5. Security checklist for production

- Set strong `JWT_SECRET_KEY` and `ENCRYPTION_KEY`  
- Use PostgreSQL: `DATABASE_URL=postgresql://user:pass@host/db`  
- Set `DEBUG=false`  
- Serve over HTTPS only  
- Never commit `.env`
