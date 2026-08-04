# Shopify → Meta Conversions API (Server-Side Tracking)

Production path inside App Manager (FastAPI), not a separate Node service. Uses the existing HMAC-verified Shopify webhook and SQLite for idempotency.

## Setup in the UI

1. Connect a Shopify store (Settings → Stores)
2. Open **Apps → Server-Side Tracking**
3. Enter **Pixel ID** + **CAPI access token** (or fall back to Analytics Meta Marketing token)
4. Align **event_id scheme** with your browser Pixel Purchase `eventID`
5. Set trigger to `orders/paid` (or `orders/create` for COD)
6. Optional: **Test event code** from Events Manager → Test Events
7. Enable and save

## Webhook

Already registered when the store connects (`orders/create`, `orders/paid`, …):

```
POST {APP_URL}/api/v1/webhooks/shopify
```

- HMAC verified (`X-Shopify-Hmac-Sha256`) before any processing
- Rate-limited per IP
- Responds quickly; Meta send runs asynchronously
- Idempotent on `X-Shopify-Webhook-Id` and in-flight/sent order id

Local tunnel:

```bash
ngrok http 8000
```

Set `APP_URL` to the ngrok HTTPS URL and reconnect/register webhooks if needed.

## Deduplication

Browser Pixel and CAPI must share the same Purchase `event_id`. Configurable schemes:

| Scheme | Value |
|--------|--------|
| `order_id` (default) | Shopify order `id` |
| `checkout_token` | `checkout_token` / `cart_token` |
| `order_name` | Order name without `#` |

## Observability

- Auth: `GET /api/v1/meta-capi/stores/{store_id}/stats`
- Event log: `GET /api/v1/meta-capi/stores/{store_id}/events`
- App health: `GET /health`

## Code map

| File | Role |
|------|------|
| `backend/app/integrations/meta/hashing.py` | PII SHA-256 normalize/hash |
| `backend/app/integrations/meta/order_mapper.py` | Shopify order → CAPI Purchase |
| `backend/app/integrations/meta/capi_client.py` | Graph `/events` + retries |
| `backend/app/services/meta_capi_service.py` | Settings, claim, async send |
| `backend/app/routes/meta_capi.py` | Authenticated API |
| `backend/app/routes/webhooks.py` | Enqueue on matching topic |

## Security

- Secrets encrypted at rest; never logged
- `.env` gitignored
- Wrong HMAC → 401, payload not processed
- 4xx from Meta → no retry; 5xx/network → exponential backoff (5s / 30s / 2min)

## Follow-ups

- Confirm storefront Pixel `eventID` scheme before going live
- Capture `_fbp` / `_fbc` as order note attributes at checkout for match quality
- Graph API version defaults to `v25.0` (current as of mid-2026)
