# Meta CAPI enrichment + theme setup

## Why Events Manager may say fbp / IP / UA / external_id are missing

App Manager **does send** these when available. Gaps usually mean Shopify’s order payload didn’t include them (common with **Phoenix / external checkout**):

| Parameter | Source | Fix |
|-----------|--------|-----|
| `fbp` / `fbc` | Cart note attributes / attribution cache | Publish theme script + theme settings (store ID + browser token) |
| `client_ip_address` / `client_user_agent` | Shopify `browser_ip` / `client_details`, else theme Attribution ping cache | Theme must load so Attribution beacon can cache IP/UA before checkout |
| `external_id` | Shopify `customer.id`, else hashed email/phone | Guest orders now fall back to email/phone |
| Date of birth (`db`) | Not on Shopify orders | Cannot send — ignore this Meta suggestion |

After publishing the theme, place a test order from an ad click and re-check EMQ in 24–48h.

---

## Reliability (never miss a sale)

App Manager runs a background worker while the API is up:

1. **Webhooks** — Purchase on `orders/paid`, plus `orders/create` / `orders/updated` when `financial_status` is paid (and InitiateCheckout on `checkouts/create`).
2. **Retries** — Failed Meta sends are retried (up to 15 attempts) every few minutes.
3. **Reconcile** — Every ~5 minutes, pulls paid Shopify orders from the last 48 hours and sends any Purchase that was never logged/sent.

Env knobs (optional): `META_CAPI_RECONCILE_SECONDS=300`, `META_CAPI_RECONCILE_HOURS=48`, `META_CAPI_MAX_SEND_ATTEMPTS=15`.

Reconnect the Shopify store after deploy so `orders/updated` is subscribed.

---

## Funnel events Meta receives

| Event | Source |
|-------|--------|
| **PageView** | Theme (once per path / session) |
| **ViewContent** | Theme product pages |
| **Search** | Theme search page / search form |
| **AddToCart** | Theme form ATC + AJAX `/cart/add.js` |
| **InitiateCheckout** | Theme on Phoenix redirect; Shopify `checkouts/create` when enabled |
| **Purchase** | Shopify paid order webhooks + reconcile worker |

Match quality: `fbp` / `fbc` / `fbclid`, IP, user agent, hashed email/phone, stable `external_id` (customer id or first-party guest id saved on the cart).

**Not available without Phoenix-side code:** AddPaymentInfo (payment step is on `secureorder…`).

---

## Theme changes (required for fbp/fbc + funnel)

Already added to `phx-3-0-checkout-builder` and `Theme_coded`:

| File | Purpose |
|------|---------|
| `assets/meta-capi-attribution.js` | Capture cookies, cart attributes, beacons |
| `snippets/meta-capi-attribution.liquid` | Config + script include |
| `layout/theme.liquid` | Renders snippet; Phoenix URL gets fbp/fbc/fbclid |
| Theme setting group **Meta CAPI (App Manager)** | Store ID + browser token |

### Deploy steps

1. Push/publish the updated theme (or copy files into the live PHX theme).
2. In App Manager → **Server-Side Tracking → Settings**, copy **Theme browser event token**.
3. In Shopify Admin → **Online Store → Themes → Customize → Theme settings → Meta CAPI (App Manager)**:
   - Enable tracking
   - API base: `https://appmanager.store/api/v1`
   - Store ID: your App Manager store UUID
   - Paste the browser event token
4. Reconnect the Shopify store in App Manager (or re-register webhooks) so `checkouts/create` is subscribed.
5. Clear **Test event code** when going live.

### Phoenix checkout note

Orders go through `secureorder.luxory.online`. The theme now:
1. Writes `_fbp` / `_fbc` / `fbclid` to **Shopify cart attributes** (become order note attributes when the order is created from that cart)
2. Appends the same values to the Phoenix checkout URL

If a specific Phoenix order is missing `fbp`/`fbc` in App Manager’s event log, confirm Phoenix is creating the Shopify order from the cart token (attributes travel with the cart).

## EMQ checklist

After a few live purchases, check Events Manager → Purchase → Event Match Quality. Aim for email + phone + fbp/fbc coverage.
