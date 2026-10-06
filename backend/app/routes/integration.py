"""Read-only API for other internal apps (Central AI).

Authenticated by INTEGRATION_API_KEY instead of a user login, and always scoped to the
stores of INTEGRATION_OWNER_EMAIL. Nothing here changes data, publishes ads or sends email.
"""

import hmac
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    AIDirectorSuggestion,
    AIEmailAssistantSettings,
    AIEmailReply,
    AIReplyStatus,
    CreativeGenerationJob,
    EmailSendLog,
    EmailSendStatus,
    InboxEmail,
    InboxEmailStatus,
    MetaCapiEventLog,
    MetaCapiEventStatus,
    OrderTracking,
    Store,
    StoreStatus,
    User,
)
from app.db.session import get_db
from app.integrations.meta.windows import ads_zone, today_in_zone
from app.services.ads_service import AdsService
from app.services.analytics_service import AnalyticsService
from app.services.tracking_service import TrackingService

router = APIRouter()
_analytics = AnalyticsService()
_ads = AdsService()
_tracking = TrackingService()

Period = Literal["today", "yesterday", "week", "month"]

PERIOD_LABELS = {
    "today": "today so far",
    "yesterday": "yesterday",
    "week": "the last 7 complete days",
    "month": "the last 30 complete days",
}


def integration_owner(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    expected = settings.integration_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The integration API is off. Set INTEGRATION_API_KEY to enable it.",
        )
    supplied = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid integration key")
    email = settings.integration_owner_email.strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set INTEGRATION_OWNER_EMAIL to the App Manager account whose stores Central AI may read.",
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTEGRATION_OWNER_EMAIL does not match an active, verified App Manager account.",
        )
    return user


def dashboard_range(period: Period, store: Store) -> dict[str, Any]:
    """Map Central AI periods onto App Manager's dashboard presets."""
    if period == "today":
        today = today_in_zone(store.timezone or settings.ai_ad_weekly_default_timezone).isoformat()
        return {"period": "custom", "custom_since": today, "custom_until": today}
    return {"period": {"yesterday": "1d", "week": "7d", "month": "30d"}[period]}


def _owned_stores(db: Session, user: User, store: str | None) -> list[Store]:
    rows = list(db.scalars(select(Store).where(Store.owner_id == user.id).order_by(Store.name)).all())
    if store:
        needle = store.strip().lower()
        rows = [
            s
            for s in rows
            if needle in (s.id.lower(), s.shop_domain.lower()) or needle in s.name.lower()
        ]
        if not rows:
            raise HTTPException(status_code=404, detail=f'No store matches "{store}"')
        return rows
    return [s for s in rows if s.status == StoreStatus.CONNECTED.value] or rows


def _store_info(store: Store) -> dict:
    return {
        "id": store.id,
        "name": store.name,
        "domain": store.shop_domain,
        "status": store.status,
        "plan": store.plan,
        "timezone": store.timezone,
        "currency": store.currency,
    }


def _pick(source: dict | None, keys: tuple[str, ...]) -> dict:
    source = source or {}
    return {key: source.get(key) for key in keys if key in source}


async def _dashboard(db: Session, user: User, store: Store, period: Period) -> dict:
    return await _analytics.get_dashboard(db, user, store.id, **dashboard_range(period, store))


def _window(period: Period, data: dict) -> dict:
    window = data.get("date_range") or {"since": data.get("since"), "until": data.get("until")}
    return {"period": period, "meaning": PERIOD_LABELS[period], **window}


SALES_KEYS = ("revenue", "revenue_source", "orders", "aov", "refunds", "shopify_revenue", "stripe_revenue_net")
PROFIT_KEYS = (
    "revenue",
    "cogs",
    "shipping_costs",
    "transaction_fees",
    "gross_profit",
    "ad_spend",
    "net_profit",
    "net_margin_pct",
    "margin_before_ads_pct",
    "mer",
    "roas",
    "cpa",
    "break_even_roas",
)


@router.get("/stores")
def list_stores(user: User = Depends(integration_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(Store).where(Store.owner_id == user.id).order_by(Store.name)).all()
    return {"stores": [_store_info(s) for s in rows]}


@router.get("/sales")
async def sales(
    period: Period = "today",
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    results = []
    for row in _owned_stores(db, user, store):
        data = await _dashboard(db, user, row, period)
        results.append(
            {
                "store": row.name,
                "currency": data.get("currency"),
                "window": _window(period, data),
                **_pick(data.get("summary"), SALES_KEYS),
                "connections": data.get("connections"),
            }
        )
    return {"period": period, "stores": results}


@router.get("/orders")
async def orders(
    period: Period = "today",
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    results = []
    for row in _owned_stores(db, user, store):
        data = await _dashboard(db, user, row, period)
        summary = data.get("summary") or {}
        results.append(
            {
                "store": row.name,
                "currency": data.get("currency"),
                "window": _window(period, data),
                "order_count": summary.get("orders"),
                "refunds": summary.get("refunds"),
                "recent_orders": [
                    _pick(o, ("order_number", "total", "profit", "created_at"))
                    for o in data.get("recent_orders") or []
                ],
            }
        )
    return {"period": period, "stores": results}


@router.get("/analytics")
async def analytics(
    period: Period = "week",
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    results = []
    for row in _owned_stores(db, user, store):
        data = await _dashboard(db, user, row, period)
        results.append(
            {
                "store": row.name,
                "currency": data.get("currency"),
                "window": _window(period, data),
                "profit": _pick(data.get("summary"), PROFIT_KEYS),
                "top_products": [
                    _pick(p, ("title", "units_sold", "revenue", "profit", "margin_pct"))
                    for p in (data.get("top_products") or [])[:5]
                ],
                "insights": [
                    _pick(i, ("level", "title", "message")) for i in (data.get("insights") or [])[:6]
                ],
            }
        )
    return {"period": period, "stores": results}


@router.get("/ads")
async def ads(
    period: Period = "week",
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    results = []
    for row in _owned_stores(db, user, store):
        data = await _ads.get_dashboard(db, user, row.id, **dashboard_range(period, row))
        summary = data.get("summary") or {}
        results.append(
            {
                "store": row.name,
                "currency": data.get("currency"),
                "window": _window(period, data),
                "meta_configured": data.get("meta_configured"),
                "meta_error": data.get("meta_error"),
                "summary": _pick(
                    summary,
                    (
                        "spend",
                        "impressions",
                        "clicks",
                        "ctr",
                        "cpm",
                        "purchases",
                        "purchase_value",
                        "platform_roas",
                        "cpa",
                        "mer",
                        "frequency",
                        "store_revenue",
                        "store_orders",
                    ),
                ),
                "top_campaigns": [
                    _pick(c, ("name", "status", "spend", "purchases", "platform_roas", "cpa"))
                    for c in sorted(data.get("campaigns") or [], key=lambda c: c.get("spend") or 0, reverse=True)[:5]
                ],
                "alerts": [_pick(a, ("severity", "title", "message")) for a in data.get("alerts") or []],
            }
        )
    return {"period": period, "stores": results}


@router.get("/shipping")
def shipping(
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    results = []
    for row in _owned_stores(db, user, store):
        data = _tracking.get_overview(db, user, row.id)
        results.append(
            {
                "store": row.name,
                **_pick(data, ("stats", "carrier_enrichment", "shopify_connected")),
            }
        )
    return {"stores": results, "as_of": date.today().isoformat()}


# Daily briefing: everything an owner would check each morning, with what looks wrong.

LATE_SHIPPING_DAYS = 4
LATE_SHIPPING_LOOKBACK_DAYS = 45
STALE_REVIEW_HOURS = 24
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
LEVEL_SEVERITY = {"danger": "high", "warning": "medium"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _count(db: Session, model, *where) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _problem(problems: list, severity: str, title: str, detail: str, page: str) -> None:
    problems.append({"severity": severity, "title": title, "detail": detail, "page": page})


def _kpi(label: str, value, **extra) -> dict:
    return {"label": label, "value": value, **{k: v for k, v in extra.items() if v is not None}}


def _local(value: datetime | None, zone) -> str | None:
    value = _aware(value)
    return value.astimezone(zone).strftime("%b %d %H:%M") if value else None


async def _sales_section(db: Session, user: User, store: Store, problems: list) -> dict:
    try:
        data = await _dashboard(db, user, store, "today")
    except Exception as exc:
        _problem(problems, "high", "Couldn't load today's sales", str(getattr(exc, "detail", exc))[:200], "dashboard")
        return {"title": "Sales today", "items": []}
    summary = data.get("summary") or {}
    currency = data.get("currency")
    revenue = summary.get("revenue") or 0
    net = summary.get("net_profit")
    if revenue and net is not None and net < 0:
        _problem(problems, "medium", "Losing money today so far", f"Net profit is {net:.2f} {currency} on {revenue:.2f} revenue.", "analytics")
    insights = []
    for insight in (data.get("insights") or [])[:6]:
        severity = LEVEL_SEVERITY.get(insight.get("level"))
        if severity:
            _problem(problems, severity, insight.get("title") or "Analytics warning", insight.get("message") or "", "analytics")
        insights.append({"title": insight.get("title"), "detail": insight.get("message"), "status": insight.get("level")})
    return {
        "title": "Sales today",
        "kpis": [
            _kpi("Revenue", revenue, currency=currency),
            _kpi("Orders", summary.get("orders") or 0),
            _kpi("Average order", summary.get("aov") or 0, currency=currency),
            _kpi("Net profit", net if net is not None else "—", currency=currency if net is not None else None),
            _kpi("Ad spend", summary.get("ad_spend") or 0, currency=currency),
            _kpi("Refunds", summary.get("refunds") or 0, currency=currency, tone="warn" if summary.get("refunds") else None),
        ],
        "items": insights,
    }


async def _ads_section(db: Session, user: User, store: Store, problems: list) -> dict:
    title = "Meta ads · last 7 days"
    try:
        data = await _ads.get_dashboard(db, user, store.id, **dashboard_range("week", store))
    except Exception as exc:
        _problem(problems, "high", "Couldn't load ads", str(getattr(exc, "detail", exc))[:200], "ads")
        return {"title": title, "items": []}
    if not data.get("meta_configured"):
        return {"title": title, "items": [{"title": "Meta ads aren't connected", "detail": "Connect Meta in App Manager settings.", "status": "off"}]}
    if data.get("meta_error"):
        _problem(problems, "high", "Meta ads returned an error", str(data["meta_error"])[:200], "ads")
    summary = data.get("summary") or {}
    currency = data.get("currency")
    spend = summary.get("spend") or 0
    roas = summary.get("platform_roas")
    if spend and roas is not None and roas < 1:
        _problem(problems, "medium", "Ads are returning less than they cost", f"Meta ROAS is {roas:.2f}x on {spend:.2f} {currency} spend this week.", "ads")
    alerts = []
    for alert in data.get("alerts") or []:
        severity = LEVEL_SEVERITY.get(alert.get("severity"))
        if severity:
            _problem(problems, severity, alert.get("title") or "Ads alert", alert.get("message") or "", "ads")
        alerts.append({"title": alert.get("title"), "detail": alert.get("message"), "status": alert.get("severity")})
    return {
        "title": title,
        "kpis": [
            _kpi("Spend", spend, currency=currency),
            _kpi("ROAS", roas if roas is not None else "—", suffix="x" if roas is not None else None),
            _kpi("Purchases", summary.get("purchases") or 0),
            _kpi("Cost per purchase", summary.get("cpa") or 0, currency=currency),
            _kpi("Frequency", summary.get("frequency") or 0, decimals=2, tone="warn" if (summary.get("frequency") or 0) >= 3.5 else None),
        ],
        "items": alerts,
    }


def _email_section(db: Session, user: User, store: Store, now: datetime, start_today: datetime, zone, problems: list) -> dict:
    mine = (InboxEmail.user_id == user.id, InboxEmail.store_id == store.id)
    held_q = InboxEmail.status == InboxEmailStatus.MANUAL_REVIEW.value
    held_total = _count(db, InboxEmail, *mine, held_q)
    held = db.scalars(select(InboxEmail).where(*mine, held_q).order_by(InboxEmail.received_at.desc()).limit(8)).all()
    drafts = _count(db, InboxEmail, *mine, InboxEmail.status == InboxEmailStatus.DRAFT_PENDING.value)
    waiting = _count(db, InboxEmail, *mine, InboxEmail.status == InboxEmailStatus.NEW.value)
    received_today = _count(db, InboxEmail, *mine, InboxEmail.received_at >= start_today)
    failed = int(
        db.scalar(
            select(func.count())
            .select_from(AIEmailReply)
            .join(InboxEmail, AIEmailReply.inbox_email_id == InboxEmail.id)
            .where(
                AIEmailReply.user_id == user.id,
                InboxEmail.store_id == store.id,
                AIEmailReply.status == AIReplyStatus.FAILED.value,
                AIEmailReply.created_at >= now - timedelta(days=7),
            )
        )
        or 0
    )
    config = db.scalar(
        select(AIEmailAssistantSettings).where(
            AIEmailAssistantSettings.user_id == user.id, AIEmailAssistantSettings.store_id == store.id
        )
    )

    if held_total:
        stale = any((_aware(e.received_at) or now) < now - timedelta(hours=STALE_REVIEW_HOURS) for e in held)
        _problem(
            problems,
            "high" if stale else "medium",
            f"{held_total} email{'s' if held_total != 1 else ''} waiting for your manual review",
            "Some have been waiting more than a day." if stale else "Cancellations, disputed charges and similar cases a person must finish.",
            "ai_email",
        )
    if failed:
        _problem(problems, "high", f"{failed} AI email repl{'ies' if failed != 1 else 'y'} failed to send this week", "Open the AI email assistant to retry them.", "ai_email")
    if drafts:
        _problem(problems, "low", f"{drafts} AI draft{'s' if drafts != 1 else ''} waiting for approval", "Review and send them in the AI email assistant.", "ai_email")

    autopilot = "Off"
    if config and config.automation_enabled:
        autopilot = "On"
        if config.automation_last_error:
            _problem(problems, "high", "Email autopilot reported an error", config.automation_last_error[:200], "ai_email")
        last_run = _aware(config.automation_last_run_at)
        overdue = timedelta(minutes=max(60, 3 * (config.automation_interval_minutes or 15)))
        if last_run is None or now - last_run > overdue:
            _problem(
                problems,
                "medium",
                "Email autopilot hasn't run recently",
                f"Last run {_local(last_run, zone) or 'never'}.",
                "ai_email",
            )

    return {
        "title": "AI email assistant",
        "kpis": [
            _kpi("Manual review", held_total, tone="warn" if held_total else "ok"),
            _kpi("Drafts to approve", drafts, tone="warn" if drafts else None),
            _kpi("Not handled yet", waiting),
            _kpi("Received today", received_today),
            _kpi("Failed replies (7d)", failed, tone="bad" if failed else "ok"),
            _kpi("Autopilot", autopilot, tone="ok" if autopilot == "On" else "warn"),
        ],
        "items": [
            {
                "title": e.subject or "(no subject)",
                "detail": " · ".join(filter(None, [e.skip_reason or "A teammate needs to finish this.", _local(e.received_at, zone)])),
                "status": "manual review",
            }
            for e in held
        ],
    }


def _operations_section(db: Session, store: Store, now: datetime, problems: list) -> dict:
    capi_failed = _count(
        db,
        MetaCapiEventLog,
        MetaCapiEventLog.store_id == store.id,
        MetaCapiEventLog.status == MetaCapiEventStatus.FAILED.value,
        MetaCapiEventLog.created_at >= now - timedelta(days=1),
    )
    mail_failed = _count(
        db,
        EmailSendLog,
        EmailSendLog.store_id == store.id,
        EmailSendLog.status == EmailSendStatus.FAILED.value,
        EmailSendLog.sent_at >= now - timedelta(days=7),
    )
    late = _count(
        db,
        OrderTracking,
        OrderTracking.store_id == store.id,
        OrderTracking.tracking_number.is_(None),
        OrderTracking.status == "pending",
        OrderTracking.order_placed_at < now - timedelta(days=LATE_SHIPPING_DAYS),
        OrderTracking.order_placed_at >= now - timedelta(days=LATE_SHIPPING_LOOKBACK_DAYS),
        func.coalesce(OrderTracking.shopify_financial_status, "").not_in(("refunded", "voided")),
    )
    ideas = _count(db, AIDirectorSuggestion, AIDirectorSuggestion.store_id == store.id, AIDirectorSuggestion.status == "NEW")
    jobs_failed = _count(
        db,
        CreativeGenerationJob,
        CreativeGenerationJob.store_id == store.id,
        CreativeGenerationJob.status == "FAILED",
        CreativeGenerationJob.created_at >= now - timedelta(days=7),
    )
    if capi_failed:
        _problem(problems, "high", f"{capi_failed} purchase event{'s' if capi_failed != 1 else ''} failed to reach Meta in 24h", "Meta can't credit those sales to your ads.", "meta_capi")
    if mail_failed:
        _problem(problems, "medium", f"{mail_failed} automated email{'s' if mail_failed != 1 else ''} failed this week", "Order or shipping emails didn't go out.", "email")
    if late:
        _problem(problems, "medium", f"{late} order{'s' if late != 1 else ''} still without tracking after {LATE_SHIPPING_DAYS} days", "Customers may start asking where their order is.", "tracking")
    if jobs_failed:
        _problem(problems, "low", f"{jobs_failed} AI ad generation job{'s' if jobs_failed != 1 else ''} failed this week", "Check AI ads progress.", "ai_ads")
    return {
        "title": "Operations",
        "kpis": [
            _kpi("Meta CAPI failures (24h)", capi_failed, tone="bad" if capi_failed else "ok"),
            _kpi("Failed automated emails (7d)", mail_failed, tone="bad" if mail_failed else "ok"),
            _kpi(f"No tracking after {LATE_SHIPPING_DAYS} days", late, tone="warn" if late else "ok"),
            _kpi("New AI ad ideas", ideas),
            _kpi("Failed AI ad jobs (7d)", jobs_failed, tone="warn" if jobs_failed else None),
        ],
        "items": [],
    }


@router.get("/briefing")
async def briefing(
    store: str | None = Query(None, max_length=255),
    user: User = Depends(integration_owner),
    db: Session = Depends(get_db),
):
    now = datetime.now(UTC)
    results = []
    for row in _owned_stores(db, user, store):
        zone = ads_zone(row.timezone or settings.ai_ad_weekly_default_timezone)
        today = today_in_zone(row.timezone or settings.ai_ad_weekly_default_timezone)
        start_today = datetime.combine(today, time.min, tzinfo=zone).astimezone(UTC)
        problems: list[dict] = []
        sections = [
            await _sales_section(db, user, row, problems),
            _email_section(db, user, row, now, start_today, zone, problems),
            await _ads_section(db, user, row, problems),
            _operations_section(db, row, now, problems),
        ]
        problems.sort(key=lambda p: SEVERITY_RANK.get(p["severity"], 3))
        results.append(
            {
                "store": row.name,
                "currency": row.currency,
                "today": today.isoformat(),
                "problems": problems,
                "sections": sections,
            }
        )
    return {
        "period": "today",
        "generated_at": now.isoformat(),
        "problem_count": sum(len(r["problems"]) for r in results),
        "stores": results,
    }
