"""Meta Ads dashboard + AI reports for e-commerce operators."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_email_assistant.ai_service import AIService
from app.ai_email_assistant.openai_errors import OpenAIServiceError
from app.config import settings
from app.core.crypto import decrypt_value, encrypt_value
from app.core.openai_credentials import (
    is_openai_configured,
    openai_key_status,
    resolve_openai_api_key,
)
from app.db.models import AdsAiReport, Store, StoreAdsSettings, StoreAnalyticsSettings, User
from app.integrations.meta.client import (
    MetaAdsClient,
    hook_rate,
    parse_meta_cpa,
    parse_meta_float,
    parse_meta_funnel,
    parse_meta_outbound_clicks,
    parse_meta_outbound_ctr,
    parse_meta_purchase_roas,
    parse_meta_purchase_value,
    parse_meta_purchases,
    parse_meta_video_3s_plays,
)
from app.integrations.shopify.client import ShopifyClient
from app.tracking.credentials import mask_api_key_hint

logger = logging.getLogger(__name__)


def _d(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _safe_div(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return (part / whole) * 100


class AdsService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def _shopify_client(self, store: Store) -> ShopifyClient | None:
        if not store.access_token_encrypted:
            return None
        try:
            token = decrypt_value(store.access_token_encrypted)
        except Exception:
            return None
        return ShopifyClient(store.shop_domain, token)

    def get_or_create_analytics_settings(self, db: Session, store_id: str) -> StoreAnalyticsSettings:
        row = db.scalar(
            select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == store_id)
        )
        if row:
            return row
        row = StoreAnalyticsSettings(store_id=store_id)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def get_or_create_ads_settings(self, db: Session, store_id: str) -> StoreAdsSettings:
        row = db.scalar(select(StoreAdsSettings).where(StoreAdsSettings.store_id == store_id))
        if row:
            return row
        row = StoreAdsSettings(store_id=store_id)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _meta_client(self, analytics: StoreAnalyticsSettings) -> MetaAdsClient | None:
        if not analytics.meta_access_token_encrypted or not analytics.meta_ad_account_id:
            return None
        try:
            token = decrypt_value(analytics.meta_access_token_encrypted)
        except Exception:
            return None
        return MetaAdsClient(token, analytics.meta_ad_account_id)

    @staticmethod
    def _masked_hint(hint: str | None, has_value: bool) -> str | None:
        if not has_value:
            return None
        return hint or "••••"

    def get_settings(self, db: Session, user: User, store_id: str) -> dict:
        self._ensure_store(db, user, store_id)
        analytics = self.get_or_create_analytics_settings(db, store_id)
        ads = self.get_or_create_ads_settings(db, store_id)
        openai = openai_key_status(user)
        meta_configured = bool(
            analytics.meta_access_token_encrypted and analytics.meta_ad_account_id
        )
        return {
            "store_id": store_id,
            "meta_configured": meta_configured,
            "meta_token_masked": self._masked_hint(
                analytics.meta_access_token_hint, bool(analytics.meta_access_token_encrypted)
            ),
            "meta_ad_account_id": analytics.meta_ad_account_id,
            "ai_reports_consent": ads.ai_reports_consent,
            "daily_ai_reports": ads.daily_ai_reports,
            "weekly_ai_reports": ads.weekly_ai_reports,
            "last_daily_report_at": ads.last_daily_report_at.isoformat()
            if ads.last_daily_report_at
            else None,
            "last_weekly_report_at": ads.last_weekly_report_at.isoformat()
            if ads.last_weekly_report_at
            else None,
            "openai_configured": openai["openai_configured"],
            "openai_key_masked": openai["openai_key_masked"],
            "openai_key_is_user_owned": openai["openai_key_is_user_owned"],
            "openai_uses_server_fallback": openai["openai_uses_server_fallback"],
        }

    def update_settings(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self._ensure_store(db, user, store_id)
        analytics = self.get_or_create_analytics_settings(db, store_id)
        ads = self.get_or_create_ads_settings(db, store_id)

        if body.get("meta_access_token") is not None:
            token = str(body["meta_access_token"]).strip()
            if token:
                analytics.meta_access_token_encrypted = encrypt_value(token)
                analytics.meta_access_token_hint = mask_api_key_hint(token)
            else:
                analytics.meta_access_token_encrypted = None
                analytics.meta_access_token_hint = None

        if body.get("meta_ad_account_id") is not None:
            account = str(body["meta_ad_account_id"]).strip().replace("act_", "")
            analytics.meta_ad_account_id = account or None

        if body.get("ai_reports_consent") is not None:
            ads.ai_reports_consent = bool(body["ai_reports_consent"])
            if not ads.ai_reports_consent:
                ads.daily_ai_reports = False
                ads.weekly_ai_reports = False

        if body.get("daily_ai_reports") is not None:
            if body["daily_ai_reports"] and not ads.ai_reports_consent:
                raise HTTPException(
                    status_code=400,
                    detail="Enable AI report consent before turning on daily reports",
                )
            ads.daily_ai_reports = bool(body["daily_ai_reports"])

        if body.get("weekly_ai_reports") is not None:
            if body["weekly_ai_reports"] and not ads.ai_reports_consent:
                raise HTTPException(
                    status_code=400,
                    detail="Enable AI report consent before turning on weekly reports",
                )
            ads.weekly_ai_reports = bool(body["weekly_ai_reports"])

        db.commit()
        return self.get_settings(db, user, store_id)

    async def test_meta_connection(
        self, db: Session, user: User, store_id: str, body: dict
    ) -> dict:
        self._ensure_store(db, user, store_id)
        row = self.get_or_create_analytics_settings(db, store_id)
        token = str(body.get("meta_access_token") or "").strip()
        account_id = str(body.get("meta_ad_account_id") or row.meta_ad_account_id or "").strip()
        if not token and row.meta_access_token_encrypted:
            token = decrypt_value(row.meta_access_token_encrypted)
        if not token:
            raise HTTPException(status_code=400, detail="Enter a Meta access token")
        if not account_id:
            raise HTTPException(status_code=400, detail="Enter your Meta ad account ID")
        client = MetaAdsClient(token, account_id)
        ok, message, name = await client.test_connection()
        return {"ok": ok, "message": message, "account_name": name}

    def _parse_range(
        self,
        period: str,
        analytics_start: str | None = None,
        *,
        store: Store | None = None,
        custom_since: str | None = None,
        custom_until: str | None = None,
    ) -> tuple[datetime, datetime, str, str]:
        now = datetime.now(UTC)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        if period == "custom":
            if not custom_since or not custom_until:
                raise HTTPException(
                    status_code=400, detail="Custom range requires since and until dates"
                )
            try:
                start = datetime.strptime(custom_since[:10], "%Y-%m-%d").replace(tzinfo=UTC)
                end = datetime.strptime(custom_until[:10], "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, microsecond=0, tzinfo=UTC
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail="Invalid date format (use YYYY-MM-DD)") from e
            if start > end:
                raise HTTPException(status_code=400, detail="Start date must be on or before end date")
        elif period == "all":
            if store and store.created_at:
                start = store.created_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
            else:
                start = datetime(2010, 1, 1, tzinfo=UTC)
        elif period == "1d":
            start = end
        elif period == "7d":
            start = end - timedelta(days=6)
        elif period == "14d":
            start = end - timedelta(days=13)
        elif period == "90d":
            start = end - timedelta(days=89)
        else:
            # 30d default
            start = end - timedelta(days=29)

        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if analytics_start and period != "custom":
            try:
                clip = datetime.strptime(analytics_start[:10], "%Y-%m-%d").replace(tzinfo=UTC)
                if clip > start:
                    start = clip
            except ValueError:
                pass
        return start, end, _iso_date(start), _iso_date(end)

    def _summarize_insight_row(self, row: dict, *, name_keys: tuple[str, ...]) -> dict:
        spend = parse_meta_float(row, "spend")
        impressions = parse_meta_float(row, "impressions")
        reach = parse_meta_float(row, "reach")
        frequency = parse_meta_float(row, "frequency")
        clicks = parse_meta_float(row, "clicks")
        purchases = parse_meta_purchases(row.get("actions"))
        purchase_value = parse_meta_purchase_value(row.get("action_values"))
        funnel = parse_meta_funnel(row.get("actions"))
        video_3s = parse_meta_video_3s_plays(row)
        outbound = parse_meta_outbound_clicks(row)
        platform_roas = parse_meta_purchase_roas(row.get("purchase_roas"))
        if platform_roas <= 0 and spend > 0 and purchase_value > 0:
            platform_roas = purchase_value / spend
        cpa = parse_meta_cpa(row, purchases)
        name = ""
        for key in name_keys:
            if row.get(key):
                name = str(row.get(key))
                break
        return {
            "id": str(row.get("ad_id") or row.get("adset_id") or row.get("campaign_id") or ""),
            "name": name,
            "campaign_id": str(row.get("campaign_id") or ""),
            "campaign_name": str(row.get("campaign_name") or ""),
            "adset_id": str(row.get("adset_id") or ""),
            "adset_name": str(row.get("adset_name") or ""),
            "spend": round(spend, 2),
            "impressions": int(impressions),
            "reach": int(reach),
            "frequency": round(frequency, 2),
            "clicks": int(clicks),
            "ctr": round(parse_meta_float(row, "ctr"), 3),
            "cpm": round(parse_meta_float(row, "cpm"), 2),
            "cpc": round(parse_meta_float(row, "cpc"), 2),
            "outbound_clicks": int(outbound),
            "outbound_ctr": round(parse_meta_outbound_ctr(row, impressions), 3),
            "hook_rate": round(hook_rate(video_3s, impressions), 2),
            "video_3s_plays": int(video_3s),
            "purchases": int(purchases),
            "purchase_value": round(purchase_value, 2),
            "platform_roas": round(platform_roas, 2),
            "cpa": round(cpa, 2),
            "add_to_cart": int(funnel["add_to_cart"]),
            "initiate_checkout": int(funnel["initiate_checkout"]),
            "view_content": int(funnel["view_content"]),
            "landing_page_views": int(funnel["landing_page_view"]),
            "quality_ranking": row.get("quality_ranking"),
            "engagement_rate_ranking": row.get("engagement_rate_ranking"),
            "conversion_rate_ranking": row.get("conversion_rate_ranking"),
        }

    def _build_alerts(self, summary: dict, ads: list[dict], campaigns: list[dict]) -> list[dict]:
        alerts: list[dict] = []
        freq = summary.get("frequency") or 0
        if freq >= 3.5:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "high_frequency",
                    "title": "Audience fatigue risk",
                    "message": (
                        f"Account frequency is {freq:.1f} (cold audiences often tire above ~3.5). "
                        "Rotate creatives or expand audience before CPA climbs."
                    ),
                }
            )

        hook = summary.get("hook_rate") or 0
        if summary.get("impressions", 0) > 5000 and hook > 0 and hook < 15:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "weak_hook",
                    "title": "Weak creative hook",
                    "message": (
                        f"Hook rate is {hook:.1f}% (3s views / impressions). "
                        "Most e-com brands miss this — below ~15–20% usually means the first "
                        "frame is not stopping the scroll."
                    ),
                }
            )

        outbound_ctr = summary.get("outbound_ctr") or 0
        if summary.get("impressions", 0) > 5000 and outbound_ctr > 0 and outbound_ctr < 0.8:
            alerts.append(
                {
                    "severity": "info",
                    "code": "low_outbound_ctr",
                    "title": "Low outbound CTR",
                    "message": (
                        f"Outbound CTR is {outbound_ctr:.2f}%. Link CTR (not all-clicks) is the "
                        "cleaner creative-pull signal Meta's default columns hide."
                    ),
                }
            )

        funnel = summary.get("funnel") or {}
        atc = funnel.get("add_to_cart") or 0
        checkout = funnel.get("initiate_checkout") or 0
        purchases = summary.get("purchases") or 0
        if atc >= 20 and checkout > 0 and _pct(checkout, atc) < 25:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "cart_dropoff",
                    "title": "Cart → checkout drop-off",
                    "message": (
                        f"Only {_pct(checkout, atc):.0f}% of add-to-carts reach checkout. "
                        "This is often a landing page, shipping, or trust issue — not an ads "
                        "targeting problem."
                    ),
                }
            )
        if checkout >= 15 and purchases >= 0 and _pct(purchases, checkout) < 30:
            alerts.append(
                {
                    "severity": "danger",
                    "code": "checkout_dropoff",
                    "title": "Checkout → purchase leak",
                    "message": (
                        f"Only {_pct(purchases, checkout):.0f}% of checkouts convert. "
                        "Inspect payment friction, AOV vs shipping, and offer clarity before "
                        "scaling spend."
                    ),
                }
            )

        mer = summary.get("mer")
        platform_roas = summary.get("platform_roas") or 0
        if mer is not None and platform_roas > 0 and mer > 0 and platform_roas > mer * 1.6:
            alerts.append(
                {
                    "severity": "info",
                    "code": "attribution_gap",
                    "title": "Platform ROAS looks inflated vs MER",
                    "message": (
                        f"Meta ROAS is {platform_roas:.2f}x but MER (store revenue ÷ ad spend) "
                        f"is {mer:.2f}x. Most shops only watch ROAS — MER is the number that "
                        "can't lie about overall efficiency."
                    ),
                }
            )

        for ad in ads[:40]:
            if ad["spend"] < 30:
                continue
            if ad["frequency"] >= 4 and ad["ctr"] < 0.8:
                alerts.append(
                    {
                        "severity": "warning",
                        "code": "creative_fatigue",
                        "title": f"Fatiguing creative: {ad['name'][:60]}",
                        "message": (
                            f"Frequency {ad['frequency']:.1f} with CTR {ad['ctr']:.2f}%. "
                            "Pause or refresh this ad before it burns more budget."
                        ),
                        "entity_id": ad["id"],
                    }
                )
            ranking = (ad.get("quality_ranking") or "").lower()
            if ranking in ("below_average", "below average", "below_average_10", "below_average_20", "below_average_35"):
                alerts.append(
                    {
                        "severity": "danger",
                        "code": "low_quality_rank",
                        "title": f"Low quality ranking: {ad['name'][:60]}",
                        "message": "Meta quality ranking is below average — expect higher CPMs and weaker delivery.",
                        "entity_id": ad["id"],
                    }
                )

        spenders = [c for c in campaigns if c["spend"] >= 50]
        if len(spenders) >= 2:
            by_roas = sorted(spenders, key=lambda c: c["platform_roas"], reverse=True)
            best, worst = by_roas[0], by_roas[-1]
            if best["platform_roas"] > 0 and worst["platform_roas"] < best["platform_roas"] * 0.4:
                alerts.append(
                    {
                        "severity": "info",
                        "code": "budget_imbalance",
                        "title": "Budget may be on weaker campaigns",
                        "message": (
                            f"“{best['name'][:40]}” ROAS {best['platform_roas']:.2f}x vs "
                            f"“{worst['name'][:40]}” {worst['platform_roas']:.2f}x. "
                            "Reallocate toward winners after checking learning phase."
                        ),
                    }
                )

        # Deduplicate by code+title
        seen: set[str] = set()
        unique: list[dict] = []
        for a in alerts:
            key = f"{a['code']}:{a['title']}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(a)
        return unique[:12]

    async def get_dashboard(
        self,
        db: Session,
        user: User,
        store_id: str,
        period: str = "30d",
        *,
        custom_since: str | None = None,
        custom_until: str | None = None,
    ) -> dict:
        store = self._ensure_store(db, user, store_id)
        analytics = self.get_or_create_analytics_settings(db, store_id)
        ads_settings = self.get_or_create_ads_settings(db, store_id)
        start_dt, end_dt, since, until = self._parse_range(
            period,
            analytics.analytics_start_date,
            store=store,
            custom_since=custom_since,
            custom_until=custom_until,
        )
        currency = (store.currency or "USD").upper()
        meta_configured = bool(
            analytics.meta_access_token_encrypted and analytics.meta_ad_account_id
        )

        # --- Shopify revenue (for MER / blended truth) ---
        store_revenue = 0.0
        store_orders = 0
        new_customers = 0
        returning_customers = 0
        shopify_error: str | None = None
        shopify = self._shopify_client(store)
        if shopify:
            try:
                orders = await shopify.list_all_orders_in_range(
                    created_at_min=start_dt.isoformat(),
                    created_at_max=end_dt.isoformat(),
                    max_pages=100 if period == "all" else 20,
                )
                for order in orders:
                    if order.get("cancelled_at"):
                        continue
                    financial = (order.get("financial_status") or "").lower()
                    if financial in ("voided", "refunded"):
                        continue
                    total = float(_d(order.get("total_price")))
                    store_revenue += total
                    store_orders += 1
                    customer = order.get("customer") or {}
                    orders_count = customer.get("orders_count")
                    try:
                        oc = int(orders_count) if orders_count is not None else 0
                    except (TypeError, ValueError):
                        oc = 0
                    if oc <= 1:
                        new_customers += 1
                    else:
                        returning_customers += 1
            except Exception as e:
                shopify_error = str(e)
                logger.warning("Ads Shopify fetch failed for %s: %s", store_id, e)

        # --- Meta insights ---
        meta_error: str | None = None
        daily: list[dict] = []
        campaigns: list[dict] = []
        adsets: list[dict] = []
        ads: list[dict] = []
        attribution: dict = {
            "purchases_1d_click": 0,
            "purchases_7d_click": 0,
            "purchases_1d_view": 0,
            "purchase_value_1d_click": 0.0,
            "purchase_value_7d_click": 0.0,
            "gap_7d_vs_1d_pct": 0.0,
        }

        totals = {
            "spend": 0.0,
            "impressions": 0.0,
            "reach": 0.0,
            "frequency": 0.0,
            "clicks": 0.0,
            "outbound_clicks": 0.0,
            "video_3s": 0.0,
            "purchases": 0.0,
            "purchase_value": 0.0,
            "add_to_cart": 0.0,
            "initiate_checkout": 0.0,
            "view_content": 0.0,
            "landing_page_views": 0.0,
            "link_clicks": 0.0,
        }

        use_meta_maximum = period == "all" and not analytics.analytics_start_date

        client = self._meta_client(analytics)
        if client:
            try:
                if use_meta_maximum:
                    total_rows = await client.get_account_insights_all(
                        date_preset="maximum", time_increment="all_days", rich=True
                    )
                    daily_rows = await client.get_account_insights_all(
                        date_preset="maximum", time_increment=1, rich=True
                    )
                    campaign_rows = await client.get_campaign_insights(
                        date_preset="maximum", rich=True
                    )
                    adset_rows = await client.get_adset_insights(date_preset="maximum")
                    ad_rows = await client.get_ad_insights(date_preset="maximum")
                else:
                    total_rows = await client.get_account_insights_all(
                        since=since, until=until, time_increment="all_days", rich=True
                    )
                    daily_rows = await client.get_account_insights_all(
                        since=since, until=until, time_increment=1, rich=True
                    )
                    campaign_rows = await client.get_campaign_insights(
                        since=since, until=until, rich=True
                    )
                    adset_rows = await client.get_adset_insights(since=since, until=until)
                    ad_rows = await client.get_ad_insights(since=since, until=until)

                for row in total_rows:
                    totals["spend"] += parse_meta_float(row, "spend")
                    totals["impressions"] += parse_meta_float(row, "impressions")
                    totals["reach"] += parse_meta_float(row, "reach")
                    totals["clicks"] += parse_meta_float(row, "clicks")
                    totals["outbound_clicks"] += parse_meta_outbound_clicks(row)
                    totals["video_3s"] += parse_meta_video_3s_plays(row)
                    totals["purchases"] += parse_meta_purchases(row.get("actions"))
                    totals["purchase_value"] += parse_meta_purchase_value(row.get("action_values"))
                    funnel = parse_meta_funnel(row.get("actions"))
                    totals["add_to_cart"] += funnel["add_to_cart"]
                    totals["initiate_checkout"] += funnel["initiate_checkout"]
                    totals["view_content"] += funnel["view_content"]
                    totals["landing_page_views"] += funnel["landing_page_view"]
                    totals["link_clicks"] += funnel["link_click"]
                    # Weighted frequency from account row when present
                    freq = parse_meta_float(row, "frequency")
                    if freq > 0:
                        totals["frequency"] = freq

                for row in daily_rows:
                    day = (row.get("date_start") or "")[:10]
                    if not day:
                        continue
                    if analytics.analytics_start_date and day < analytics.analytics_start_date:
                        continue
                    spend = parse_meta_float(row, "spend")
                    impressions = parse_meta_float(row, "impressions")
                    purchases = parse_meta_purchases(row.get("actions"))
                    purchase_value = parse_meta_purchase_value(row.get("action_values"))
                    video_3s = parse_meta_video_3s_plays(row)
                    daily.append(
                        {
                            "date": day,
                            "spend": round(spend, 2),
                            "impressions": int(impressions),
                            "clicks": int(parse_meta_float(row, "clicks")),
                            "cpm": round(parse_meta_float(row, "cpm"), 2),
                            "ctr": round(parse_meta_float(row, "ctr"), 3),
                            "frequency": round(parse_meta_float(row, "frequency"), 2),
                            "outbound_ctr": round(parse_meta_outbound_ctr(row, impressions), 3),
                            "hook_rate": round(hook_rate(video_3s, impressions), 2),
                            "purchases": int(purchases),
                            "purchase_value": round(purchase_value, 2),
                            "cpa": round(
                                (spend / purchases) if purchases > 0 else 0.0,
                                2,
                            ),
                        }
                    )
                daily.sort(key=lambda d: d["date"])
                if period == "all" and daily and not analytics.analytics_start_date:
                    since = daily[0]["date"]

                campaigns = [
                    self._summarize_insight_row(r, name_keys=("campaign_name",))
                    for r in campaign_rows
                ]
                campaigns.sort(key=lambda c: c["spend"], reverse=True)

                adsets = [
                    self._summarize_insight_row(r, name_keys=("adset_name", "campaign_name"))
                    for r in adset_rows
                ]
                adsets.sort(key=lambda a: a["spend"], reverse=True)

                ads = [
                    self._summarize_insight_row(r, name_keys=("ad_name", "adset_name"))
                    for r in ad_rows
                ]
                ads.sort(key=lambda a: a["spend"], reverse=True)

                try:
                    if use_meta_maximum:
                        attr_rows = await client.get_account_insights_attribution(
                            date_preset="maximum"
                        )
                    else:
                        attr_rows = await client.get_account_insights_attribution(
                            since=since, until=until
                        )
                    if attr_rows:
                        # When attribution windows are requested, Meta returns action values
                        # with per-window breakdowns inside each action entry.
                        row = attr_rows[0]
                        for action in row.get("actions") or []:
                            atype = action.get("action_type") or ""
                            if atype not in (
                                "omni_purchase",
                                "purchase",
                                "offsite_conversion.fb_pixel_purchase",
                            ):
                                continue
                            attribution["purchases_1d_click"] = int(
                                float(action.get("1d_click") or action.get("value") or 0)
                            )
                            attribution["purchases_7d_click"] = int(
                                float(action.get("7d_click") or 0)
                            )
                            attribution["purchases_1d_view"] = int(
                                float(action.get("1d_view") or 0)
                            )
                            break
                        for action in row.get("action_values") or []:
                            atype = action.get("action_type") or ""
                            if atype not in (
                                "omni_purchase",
                                "purchase",
                                "offsite_conversion.fb_pixel_purchase",
                            ):
                                continue
                            attribution["purchase_value_1d_click"] = round(
                                float(action.get("1d_click") or action.get("value") or 0), 2
                            )
                            attribution["purchase_value_7d_click"] = round(
                                float(action.get("7d_click") or 0), 2
                            )
                            break
                        p1 = attribution["purchases_1d_click"]
                        p7 = attribution["purchases_7d_click"]
                        if p1 > 0:
                            attribution["gap_7d_vs_1d_pct"] = round(((p7 - p1) / p1) * 100, 1)
                except Exception as attr_err:
                    logger.info("Attribution window fetch skipped: %s", attr_err)

            except httpx.HTTPStatusError as e:
                err = {}
                try:
                    err = e.response.json().get("error") or {}
                except Exception:
                    pass
                meta_error = err.get("message") or str(e)
            except Exception as e:
                meta_error = str(e)
                logger.exception("Ads Meta fetch failed")

        spend = totals["spend"]
        impressions = totals["impressions"]
        purchases = totals["purchases"]
        purchase_value = totals["purchase_value"]
        platform_roas = _safe_div(purchase_value, spend) if spend else 0.0
        # Prefer Meta-reported ROAS from first total row when available — already folded above
        cpa = _safe_div(spend, purchases) if purchases else 0.0
        mer = _safe_div(store_revenue, spend) if spend else None
        blended_cac = _safe_div(spend, new_customers) if new_customers else None
        hook = hook_rate(totals["video_3s"], impressions)
        outbound_ctr = (
            (totals["outbound_clicks"] / impressions) * 100 if impressions > 0 else 0.0
        )
        ctr = _safe_div(totals["clicks"], impressions) * 100 if impressions else 0.0
        cpm = _safe_div(spend, impressions) * 1000 if impressions else 0.0
        frequency = totals["frequency"]
        if frequency <= 0 and totals["reach"] > 0:
            frequency = impressions / totals["reach"]

        funnel = {
            "view_content": int(totals["view_content"]),
            "landing_page_views": int(totals["landing_page_views"]),
            "link_clicks": int(totals["link_clicks"] or totals["outbound_clicks"]),
            "add_to_cart": int(totals["add_to_cart"]),
            "initiate_checkout": int(totals["initiate_checkout"]),
            "purchases": int(purchases),
            "view_to_cart_pct": round(_pct(totals["add_to_cart"], totals["view_content"] or totals["landing_page_views"]), 1),
            "cart_to_checkout_pct": round(_pct(totals["initiate_checkout"], totals["add_to_cart"]), 1),
            "checkout_to_purchase_pct": round(_pct(purchases, totals["initiate_checkout"]), 1),
        }

        summary = {
            "spend": round(spend, 2),
            "impressions": int(impressions),
            "reach": int(totals["reach"]),
            "frequency": round(frequency, 2),
            "clicks": int(totals["clicks"]),
            "ctr": round(ctr, 3),
            "cpm": round(cpm, 2),
            "outbound_clicks": int(totals["outbound_clicks"]),
            "outbound_ctr": round(outbound_ctr, 3),
            "hook_rate": round(hook, 2),
            "video_3s_plays": int(totals["video_3s"]),
            "purchases": int(purchases),
            "purchase_value": round(purchase_value, 2),
            "platform_roas": round(platform_roas, 2),
            "cpa": round(cpa, 2),
            "store_revenue": round(store_revenue, 2),
            "store_orders": store_orders,
            "mer": round(mer, 2) if mer is not None else None,
            "new_customers": new_customers,
            "returning_customers": returning_customers,
            "blended_ncac": round(blended_cac, 2) if blended_cac is not None else None,
            "funnel": funnel,
        }

        # Creative winners / losers
        creative_pool = [a for a in ads if a["spend"] >= 20]
        winners = sorted(
            [a for a in creative_pool if a["platform_roas"] > 0 or a["hook_rate"] > 0],
            key=lambda a: (a["platform_roas"], a["hook_rate"]),
            reverse=True,
        )[:5]
        needs_check = sorted(
            [
                a
                for a in creative_pool
                if a["frequency"] >= 3.2 or (a["spend"] > 50 and a["platform_roas"] < 1)
            ],
            key=lambda a: (a["frequency"], -a["platform_roas"]),
            reverse=True,
        )[:5]

        alerts = self._build_alerts(summary, ads, campaigns)

        missed_angles = [
            {
                "id": "mer",
                "title": "MER vs platform ROAS",
                "why": "ROAS is inflated by view-through + retargeting self-attribution. MER (store revenue ÷ ad spend) is immune.",
                "value": f"{summary['mer']:.2f}x" if summary["mer"] is not None else "Connect Shopify",
                "compare": f"Meta ROAS {summary['platform_roas']:.2f}x",
            },
            {
                "id": "hook_rate",
                "title": "Hook rate (3s / impressions)",
                "why": "Unaffected by iOS attribution noise — tells you if creative actually stops the scroll.",
                "value": f"{summary['hook_rate']:.1f}%",
                "compare": "Healthy cold creative often sits ~20%+",
            },
            {
                "id": "frequency",
                "title": "Frequency / fatigue",
                "why": "Most shops watch CPC and miss that high frequency is the canary before CPA blows up.",
                "value": f"{summary['frequency']:.2f}",
                "compare": "Watch cold audiences above ~3.5 in 7 days",
            },
            {
                "id": "outbound_ctr",
                "title": "Outbound CTR",
                "why": "All-clicks CTR mixes likes/comments. Outbound CTR measures real site interest.",
                "value": f"{summary['outbound_ctr']:.2f}%",
                "compare": "Use this for creative pull, not vanity CTR",
            },
            {
                "id": "attribution_gap",
                "title": "1-day vs 7-day click gap",
                "why": "The gap between windows is your modeling delta — how much Meta may be overstating.",
                "value": f"+{attribution['gap_7d_vs_1d_pct']:.0f}%"
                if attribution["gap_7d_vs_1d_pct"]
                else "—",
                "compare": f"{attribution['purchases_1d_click']} (1d) → {attribution['purchases_7d_click']} (7d)",
            },
            {
                "id": "ncac",
                "title": "New customer CAC",
                "why": "ROAS hides whether spend buys new customers or just retargets buyers.",
                "value": (
                    f"{currency} {summary['blended_ncac']:.2f}"
                    if summary["blended_ncac"] is not None
                    else "Need new-customer orders"
                ),
                "compare": f"{new_customers} new / {returning_customers} returning",
            },
        ]

        latest_report = db.scalar(
            select(AdsAiReport)
            .where(AdsAiReport.store_id == store_id)
            .order_by(AdsAiReport.created_at.desc())
            .limit(1)
        )

        return {
            "store_id": store_id,
            "period": period,
            "since": since,
            "until": until,
            "currency": currency,
            "meta_configured": meta_configured,
            "meta_error": meta_error,
            "shopify_error": shopify_error,
            "summary": summary,
            "attribution": attribution,
            "daily": daily,
            "campaigns": campaigns[:50],
            "adsets": adsets[:50],
            "ads": ads[:100],
            "winners": winners,
            "needs_check": needs_check,
            "alerts": alerts,
            "missed_angles": missed_angles,
            "ai": {
                "consent": ads_settings.ai_reports_consent,
                "daily_enabled": ads_settings.daily_ai_reports,
                "weekly_enabled": ads_settings.weekly_ai_reports,
                "openai_configured": is_openai_configured(user),
                "latest_report": self._serialize_report(latest_report) if latest_report else None,
            },
        }

    @staticmethod
    def _serialize_report(row: AdsAiReport) -> dict:
        return {
            "id": row.id,
            "report_type": row.report_type,
            "period": row.period,
            "title": row.title,
            "summary": row.summary,
            "body_markdown": row.body_markdown,
            "model_used": row.model_used,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def list_reports(self, db: Session, user: User, store_id: str, limit: int = 20) -> list[dict]:
        self._ensure_store(db, user, store_id)
        rows = db.scalars(
            select(AdsAiReport)
            .where(AdsAiReport.store_id == store_id)
            .order_by(AdsAiReport.created_at.desc())
            .limit(limit)
        ).all()
        return [self._serialize_report(r) for r in rows]

    def _build_ai_prompt(self, dashboard: dict, report_type: str) -> tuple[str, str]:
        summary = dashboard.get("summary") or {}
        alerts = dashboard.get("alerts") or []
        campaigns = (dashboard.get("campaigns") or [])[:10]
        ads = (dashboard.get("ads") or [])[:15]
        missed = dashboard.get("missed_angles") or []
        attribution = dashboard.get("attribution") or {}

        system = (
            "You are an expert Meta Ads analyst for e-commerce brands. "
            "Write clear, actionable reports for a store owner who is not a media buyer. "
            "Prefer MER, nCAC, hook rate, frequency, outbound CTR, and funnel drop-offs over vanity metrics. "
            "Call out what looks healthy vs what needs checking. "
            "Never invent numbers — only use the JSON provided. "
            "Respond in Markdown with sections: Executive summary, What's working, "
            "Needs attention, Creative notes, Recommended actions (3–5 bullets)."
        )
        payload = {
            "report_type": report_type,
            "period": dashboard.get("period"),
            "range": {"since": dashboard.get("since"), "until": dashboard.get("until")},
            "currency": dashboard.get("currency"),
            "summary": summary,
            "attribution": attribution,
            "alerts": alerts,
            "missed_angles": missed,
            "top_campaigns": campaigns,
            "top_ads": ads,
            "winners": dashboard.get("winners") or [],
            "needs_check": dashboard.get("needs_check") or [],
        }
        user_msg = (
            f"Generate a {report_type.replace('_', ' ')} Meta Ads performance report "
            f"for this e-commerce store.\n\n"
            f"DATA:\n```json\n{json.dumps(payload, default=str)[:14000]}\n```"
        )
        return system, user_msg

    async def generate_ai_report(
        self,
        db: Session,
        user: User,
        store_id: str,
        *,
        report_type: str = "on_demand",
        period: str = "7d",
        custom_since: str | None = None,
        custom_until: str | None = None,
    ) -> dict:
        self._ensure_store(db, user, store_id)
        ads_settings = self.get_or_create_ads_settings(db, store_id)

        if report_type in ("daily", "weekly") and not ads_settings.ai_reports_consent:
            raise HTTPException(
                status_code=400,
                detail="Enable AI report consent in Ads settings first",
            )
        if report_type == "on_demand" and not ads_settings.ai_reports_consent:
            raise HTTPException(
                status_code=400,
                detail="Accept AI report consent to use your OpenAI key for ads analysis",
            )

        api_key = resolve_openai_api_key(user)
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key in AI Email Assistant → Business context first",
            )

        dashboard = await self.get_dashboard(
            db,
            user,
            store_id,
            period,
            custom_since=custom_since,
            custom_until=custom_until,
        )
        if not dashboard.get("meta_configured"):
            raise HTTPException(status_code=400, detail="Connect Meta Ads before generating a report")

        system, user_msg = self._build_ai_prompt(dashboard, report_type)
        model = settings.openai_model
        ai = AIService(model=model, api_key=api_key)

        try:
            body = await ai._chat_completion(
                system_message=system,
                user_message=user_msg,
                model=model,
                temperature=0.35,
            )
        except OpenAIServiceError as e:
            raise HTTPException(status_code=502, detail=e.user_message) from e

        # Extract a short summary (first paragraph)
        summary_lines = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if summary_lines:
                    break
                continue
            summary_lines.append(stripped)
            if len(" ".join(summary_lines)) > 280:
                break
        summary = " ".join(summary_lines)[:400]
        period_labels = {
            "1d": "Daily",
            "7d": "7-day",
            "14d": "14-day",
            "30d": "30-day",
            "90d": "90-day",
            "all": "All-time",
            "custom": "Custom-range",
        }
        range_note = ""
        if dashboard.get("since") and dashboard.get("until"):
            range_note = f" ({dashboard['since']} → {dashboard['until']})"
        title_map = {
            "daily": "Daily Ads Report",
            "weekly": "Weekly Ads Report",
            "on_demand": f"{period_labels.get(period, 'Ads')} Report{range_note}",
        }
        report = AdsAiReport(
            store_id=store_id,
            user_id=user.id,
            report_type=report_type,
            period=period,
            title=title_map.get(report_type, "Ads Report"),
            summary=summary,
            body_markdown=body.strip(),
            model_used=model,
        )
        db.add(report)
        now = datetime.now(UTC)
        if report_type == "daily":
            ads_settings.last_daily_report_at = now
        elif report_type == "weekly":
            ads_settings.last_weekly_report_at = now
        db.commit()
        db.refresh(report)
        return self._serialize_report(report)

    async def maybe_run_scheduled_reports(
        self, db: Session, user: User, store_id: str
    ) -> list[dict]:
        """Generate daily/weekly reports if due when the client opens Ads (opt-in)."""
        ads_settings = self.get_or_create_ads_settings(db, store_id)
        if not ads_settings.ai_reports_consent:
            return []
        if not resolve_openai_api_key(user):
            return []

        now = datetime.now(UTC)
        created: list[dict] = []

        if ads_settings.daily_ai_reports:
            due = (
                ads_settings.last_daily_report_at is None
                or (now - ads_settings.last_daily_report_at) >= timedelta(hours=20)
            )
            if due:
                try:
                    created.append(
                        await self.generate_ai_report(
                            db, user, store_id, report_type="daily", period="7d"
                        )
                    )
                except HTTPException as e:
                    logger.info("Daily ads report skipped: %s", e.detail)

        if ads_settings.weekly_ai_reports:
            due = (
                ads_settings.last_weekly_report_at is None
                or (now - ads_settings.last_weekly_report_at) >= timedelta(days=6, hours=12)
            )
            if due:
                try:
                    created.append(
                        await self.generate_ai_report(
                            db, user, store_id, report_type="weekly", period="30d"
                        )
                    )
                except HTTPException as e:
                    logger.info("Weekly ads report skipped: %s", e.detail)

        return created
