from datetime import UTC, datetime, timedelta
import logging

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AIEmailAssistantSettings,
    AIEmailReply,
    AIReplyStatus,
    CreativeAsset,
    EmailAutomationRule,
    EmailSendLog,
    EmailSendStatus,
    GmailAccount,
    GmailAccountStatus,
    GmailStoreLink,
    InboxEmail,
    InboxEmailStatus,
    MetaCapiEventLog,
    MetaCapiEventStatus,
    OrderTracking,
    Store,
    StoreStatus,
    User,
    WebhookLog,
)

logger = logging.getLogger(__name__)


class OverviewMetric(BaseModel):
    label: str
    value: str
    change: str
    trend: str  # up | down | neutral


class SetupStep(BaseModel):
    id: str
    label: str
    done: bool
    href: str


class ModuleHighlight(BaseModel):
    slug: str
    name: str
    status: str  # active | setup | coming_soon
    stat_label: str
    stat_value: str
    hint: str


class MoneyPulse(BaseModel):
    period: str = "7d"
    currency: str = "USD"
    available: bool = False
    revenue: float = 0
    net_profit: float = 0
    ad_spend: float = 0
    roas: float = 0
    mer: float | None = None
    orders: int = 0
    hint: str = ""


class DashboardOverviewResponse(BaseModel):
    metrics: list[OverviewMetric]
    setup_steps: list[SetupStep]
    highlights: list[ModuleHighlight]
    money: MoneyPulse = MoneyPulse()


class ActivityItem(BaseModel):
    id: str
    title: str
    description: str
    timestamp: str
    type: str  # order | email | store | system


class AppModule(BaseModel):
    id: str
    name: str
    description: str
    slug: str
    status: str  # active | beta | coming_soon | setup
    icon: str


def _neutral_metric(label: str, value: int, change: str = "No data yet") -> OverviewMetric:
    return OverviewMetric(
        label=label,
        value=str(value),
        change=change,
        trend="neutral",
    )


def _format_activity_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} hr ago"
    return f"{seconds // 86400} days ago"


def _webhook_title(topic: str) -> tuple[str, str]:
    mapping = {
        "orders/create": ("New Shopify order", "order"),
        "orders/updated": ("Order updated", "order"),
        "orders/paid": ("Order paid", "order"),
        "checkouts/create": ("Checkout started", "order"),
        "fulfillments/create": ("Fulfillment created", "order"),
        "fulfillments/update": ("Fulfillment updated", "order"),
        "app/uninstalled": ("Store disconnected", "store"),
    }
    return mapping.get(topic, (topic.replace("/", " ").title(), "system"))


def _fmt_money(amount: float, currency: str) -> str:
    code = (currency or "USD").upper()
    symbol = {"USD": "$", "CAD": "CA$", "GBP": "£", "EUR": "€"}.get(code, f"{code} ")
    n = float(amount or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1000:
        return f"{sign}{symbol}{n:,.0f}"
    return f"{sign}{symbol}{n:,.2f}"


def _fmt_ratio(value: float) -> str:
    n = float(value or 0)
    return f"{n:.2f}x"


class DashboardService:
    def _store_filter(self, db: Session, user: User, store_id: str | None):
        q = select(Store.id).where(Store.owner_id == user.id)
        if store_id:
            q = q.where(Store.id == store_id)
        return list(db.scalars(q).all())

    async def get_overview(
        self, db: Session, user: User, store_id: str | None = None
    ) -> DashboardOverviewResponse:
        store_ids = self._store_filter(db, user, store_id)
        week_ago = datetime.now(UTC) - timedelta(days=7)
        primary_store_id = store_id or (store_ids[0] if store_ids else None)

        stores_owned = db.scalar(
            select(func.count())
            .select_from(Store)
            .where(
                Store.owner_id == user.id,
                *([Store.id == store_id] if store_id else []),
            )
        ) or 0
        stores_connected = db.scalar(
            select(func.count())
            .select_from(Store)
            .where(
                Store.owner_id == user.id,
                Store.status == StoreStatus.CONNECTED.value,
                *([Store.id == store_id] if store_id else []),
            )
        ) or 0

        gmail_connected = (
            db.scalar(
                select(func.count())
                .select_from(GmailAccount)
                .where(
                    GmailAccount.owner_id == user.id,
                    GmailAccount.status == GmailAccountStatus.CONNECTED.value,
                )
            )
            or 0
        )
        has_store = stores_owned > 0
        has_gmail = gmail_connected > 0

        # Gmail for this overview scope must be linked to the store(s), not just any user account
        if store_id:
            store_gmail_linked = (
                db.scalar(
                    select(func.count())
                    .select_from(GmailStoreLink)
                    .join(GmailAccount, GmailAccount.id == GmailStoreLink.gmail_account_id)
                    .where(
                        GmailStoreLink.store_id == store_id,
                        GmailAccount.owner_id == user.id,
                        GmailAccount.status == GmailAccountStatus.CONNECTED.value,
                    )
                )
                or 0
            ) > 0
        else:
            store_gmail_linked = (
                db.scalar(
                    select(func.count())
                    .select_from(GmailStoreLink)
                    .join(Store, Store.id == GmailStoreLink.store_id)
                    .join(GmailAccount, GmailAccount.id == GmailStoreLink.gmail_account_id)
                    .where(
                        Store.owner_id == user.id,
                        GmailAccount.owner_id == user.id,
                        GmailAccount.status == GmailAccountStatus.CONNECTED.value,
                    )
                )
                or 0
            ) > 0

        email_apps_ready = store_gmail_linked

        orders_synced = 0
        orders_with_tracking = 0
        orders_in_transit = 0
        capi_sent_today = 0
        creatives_week = 0
        automation_sent_week = 0
        automation_rules_on = 0
        if store_ids:
            orders_synced = (
                db.scalar(
                    select(func.count())
                    .select_from(OrderTracking)
                    .where(OrderTracking.store_id.in_(store_ids))
                )
                or 0
            )
            orders_with_tracking = (
                db.scalar(
                    select(func.count())
                    .select_from(OrderTracking)
                    .where(
                        OrderTracking.store_id.in_(store_ids),
                        OrderTracking.tracking_number.isnot(None),
                        OrderTracking.tracking_number != "",
                    )
                )
                or 0
            )
            orders_in_transit = (
                db.scalar(
                    select(func.count())
                    .select_from(OrderTracking)
                    .where(
                        OrderTracking.store_id.in_(store_ids),
                        OrderTracking.status.in_(
                            ("in_transit", "out_for_delivery", "shipped")
                        ),
                    )
                )
                or 0
            )
            capi_sent_today = (
                db.scalar(
                    select(func.count())
                    .select_from(MetaCapiEventLog)
                    .where(
                        MetaCapiEventLog.store_id.in_(store_ids),
                        MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
                        MetaCapiEventLog.sent_at >= datetime.now(UTC).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        ),
                    )
                )
                or 0
            )
            creatives_week = (
                db.scalar(
                    select(func.count())
                    .select_from(CreativeAsset)
                    .where(
                        CreativeAsset.store_id.in_(store_ids),
                        CreativeAsset.created_at >= week_ago,
                    )
                )
                or 0
            )
            automation_sent_week = (
                db.scalar(
                    select(func.count())
                    .select_from(EmailSendLog)
                    .where(
                        EmailSendLog.store_id.in_(store_ids),
                        EmailSendLog.status == EmailSendStatus.SENT.value,
                        EmailSendLog.sent_at >= week_ago,
                    )
                )
                or 0
            )
            automation_rules_on = (
                db.scalar(
                    select(func.count())
                    .select_from(EmailAutomationRule)
                    .where(
                        EmailAutomationRule.store_id.in_(store_ids),
                        EmailAutomationRule.is_enabled.is_(True),
                    )
                )
                or 0
            )

        # AI Email Assistant sends are store-scoped (inbox_emails.store_id).
        ai_sent_week = 0
        if store_ids:
            ai_sent_q = (
                select(func.count())
                .select_from(AIEmailReply)
                .join(InboxEmail, InboxEmail.id == AIEmailReply.inbox_email_id)
                .where(
                    AIEmailReply.user_id == user.id,
                    AIEmailReply.status == AIReplyStatus.SENT.value,
                    AIEmailReply.sent_at.isnot(None),
                    AIEmailReply.sent_at >= week_ago,
                    InboxEmail.store_id.in_(store_ids),
                )
            )
            ai_sent_week = db.scalar(ai_sent_q) or 0

        emails_sent_week = automation_sent_week + ai_sent_week

        inbox_q = select(func.count()).select_from(InboxEmail).where(
            InboxEmail.user_id == user.id,
            InboxEmail.status.in_(
                [
                    InboxEmailStatus.NEW.value,
                    InboxEmailStatus.DRAFT_PENDING.value,
                    InboxEmailStatus.MANUAL_REVIEW.value,
                ]
            ),
        )
        if store_id:
            inbox_q = inbox_q.where(InboxEmail.store_id == store_id)
        elif store_ids:
            inbox_q = inbox_q.where(InboxEmail.store_id.in_(store_ids))
        else:
            inbox_q = inbox_q.where(InboxEmail.store_id.is_(None))
        inbox_needs_attention = db.scalar(inbox_q) or 0

        ai_settings_q = select(AIEmailAssistantSettings).where(
            AIEmailAssistantSettings.user_id == user.id
        )
        if store_id:
            ai_settings_q = ai_settings_q.where(AIEmailAssistantSettings.store_id == store_id)
        else:
            # Prefer any store-scoped settings over legacy user-wide rows
            ai_settings_q = ai_settings_q.where(AIEmailAssistantSettings.store_id.isnot(None))
        ai_settings = db.scalar(ai_settings_q)
        ai_automation_on = bool(ai_settings and ai_settings.automation_enabled)

        money = await self._money_pulse(db, user, primary_store_id)
        currency = money.currency

        tracking_hint = (
            "Connect a Shopify store to sync orders"
            if not has_store
            else "No orders synced yet"
            if orders_synced == 0
            else f"{orders_in_transit} in transit · {orders_with_tracking} with tracking"
        )
        if not has_gmail and emails_sent_week == 0:
            email_hint = "Connect Gmail for automations"
        elif not email_apps_ready and emails_sent_week == 0:
            email_hint = "Link Gmail to this store in Settings"
        elif emails_sent_week == 0:
            email_hint = "No sends this week"
        elif automation_sent_week and ai_sent_week:
            email_hint = f"{automation_sent_week} automation · {ai_sent_week} AI replies"
        elif ai_sent_week:
            email_hint = "AI Email Assistant replies (7 days)"
        else:
            email_hint = "Email Automation sends (7 days)"

        if money.available:
            metrics = [
                OverviewMetric(
                    label="Revenue (7d)",
                    value=_fmt_money(money.revenue, currency),
                    change=f"{money.orders} orders",
                    trend="up" if money.revenue > 0 else "neutral",
                ),
                OverviewMetric(
                    label="Net profit (7d)",
                    value=_fmt_money(money.net_profit, currency),
                    change="After ads and costs",
                    trend="up" if money.net_profit > 0 else "down" if money.net_profit < 0 else "neutral",
                ),
                OverviewMetric(
                    label="Ad spend (7d)",
                    value=_fmt_money(money.ad_spend, currency),
                    change=f"ROAS {_fmt_ratio(money.roas)}" if money.ad_spend else "No Meta spend in range",
                    trend="neutral",
                ),
                OverviewMetric(
                    label="ROAS (7d)",
                    value=_fmt_ratio(money.roas) if money.ad_spend else "—",
                    change=(
                        f"MER {money.mer:.2f}x"
                        if money.mer
                        else "Revenue ÷ ad spend"
                    ),
                    trend="up" if money.roas >= 2 else "down" if money.ad_spend and money.roas < 1 else "neutral",
                ),
            ]
        else:
            metrics = [
                _neutral_metric(
                    "Connected stores",
                    stores_connected,
                    "Add a store in Settings" if stores_connected == 0 else "Shopify linked",
                ),
                _neutral_metric(
                    "Gmail accounts",
                    gmail_connected,
                    "Connect Gmail in Settings" if gmail_connected == 0 else "Ready for email apps",
                ),
                _neutral_metric("Orders synced", orders_synced, tracking_hint),
                _neutral_metric(
                    "Emails sent (7d)",
                    emails_sent_week,
                    email_hint,
                ),
            ]

        setup_steps = [
            SetupStep(
                id="store",
                label="Connect Shopify store",
                done=has_store,
                href="/settings/stores",
            ),
            SetupStep(
                id="gmail",
                label="Connect Gmail",
                done=has_gmail,
                href="/settings/gmail",
            ),
        ]

        store_apps_ready = has_store
        highlights: list[ModuleHighlight] = [
            ModuleHighlight(
                slug="analytics",
                name="Analytics",
                status="active" if store_apps_ready else "setup",
                stat_label="Revenue · 7d",
                stat_value=_fmt_money(money.revenue, currency) if money.available else "—",
                hint=(
                    f"Profit {_fmt_money(money.net_profit, currency)}"
                    if money.available
                    else "Open Analytics to load P&L"
                ),
            ),
            ModuleHighlight(
                slug="ads",
                name="Ads",
                status="active" if store_apps_ready else "setup",
                stat_label="Ad spend · 7d",
                stat_value=_fmt_money(money.ad_spend, currency) if money.available else "—",
                hint=(
                    f"ROAS {_fmt_ratio(money.roas)}"
                    if money.available and money.ad_spend
                    else "Connect Meta in Ads to see spend"
                ),
            ),
            ModuleHighlight(
                slug="ai-ads",
                name="AI Ads",
                status="active" if store_apps_ready else "setup",
                stat_label="Creatives this week",
                stat_value=str(creatives_week),
                hint="New image and video concepts" if store_apps_ready else "Connect a store to generate ads",
            ),
            ModuleHighlight(
                slug="tracking",
                name="Tracking",
                status="active" if store_apps_ready else "setup",
                stat_label="In transit",
                stat_value=str(orders_in_transit),
                hint=f"{orders_synced} orders synced" if orders_synced else tracking_hint,
            ),
            ModuleHighlight(
                slug="ai-email",
                name="AI Email Assistant",
                status="active" if email_apps_ready else "setup",
                stat_label="Inbox to review",
                stat_value=str(inbox_needs_attention),
                hint=(
                    f"{ai_sent_week} replies sent · 7d"
                    if email_apps_ready
                    else "Link Gmail to this store"
                ),
            ),
            ModuleHighlight(
                slug="email",
                name="Email Automation",
                status="active" if email_apps_ready else "setup",
                stat_label="Sends · 7d",
                stat_value=str(automation_sent_week),
                hint=(
                    f"{automation_rules_on} rules on"
                    if email_apps_ready
                    else "Link Gmail to this store"
                ),
            ),
            ModuleHighlight(
                slug="meta-capi",
                name="Server-Side Tracking",
                status="active" if store_apps_ready else "setup",
                stat_label="CAPI events today",
                stat_value=str(capi_sent_today),
                hint="Purchase events to Meta" if store_apps_ready else "Connect a store to send events",
            ),
        ]

        return DashboardOverviewResponse(
            metrics=metrics,
            setup_steps=setup_steps,
            highlights=highlights,
            money=money,
        )

    async def _money_pulse(
        self, db: Session, user: User, store_id: str | None
    ) -> MoneyPulse:
        if not store_id:
            return MoneyPulse(hint="Connect a store to see revenue and ad spend.")
        try:
            from app.services.analytics_service import AnalyticsService

            dash = await AnalyticsService().get_dashboard(db, user, store_id, "7d")
            summary = dash.get("summary") or {}
            currency = str(
                dash.get("display_currency") or dash.get("currency") or "USD"
            )
            revenue = float(summary.get("revenue") or 0)
            profit = float(summary.get("net_profit") or 0)
            spend = float(summary.get("ad_spend") or 0)
            roas = float(summary.get("roas") or 0)
            mer_raw = summary.get("mer")
            mer = float(mer_raw) if mer_raw is not None else None
            orders = int(summary.get("orders") or 0)
            hint = (
                f"Last 7 days: {_fmt_money(revenue, currency)} in, "
                f"{_fmt_money(spend, currency)} ads, "
                f"{_fmt_money(profit, currency)} profit."
            )
            return MoneyPulse(
                available=True,
                currency=currency,
                revenue=revenue,
                net_profit=profit,
                ad_spend=spend,
                roas=roas,
                mer=mer,
                orders=orders,
                hint=hint,
            )
        except Exception:
            logger.exception("Overview money pulse skipped for store %s", store_id)
            return MoneyPulse(hint="Open Analytics to load P&L for this store.")

    async def get_activity_feed(
        self, db: Session, user: User, store_id: str | None = None, limit: int = 10
    ) -> list[ActivityItem]:
        store_ids = self._store_filter(db, user, store_id)
        if not store_ids:
            return []

        logs = db.scalars(
            select(WebhookLog)
            .where(WebhookLog.store_id.in_(store_ids))
            .order_by(WebhookLog.received_at.desc())
            .limit(limit)
        ).all()

        items: list[ActivityItem] = []
        for log in logs:
            title, event_type = _webhook_title(log.topic)
            preview = (log.payload_preview or "").strip()
            if preview.startswith("{") or preview.startswith("["):
                preview = ""
            items.append(
                ActivityItem(
                    id=log.id,
                    title=title,
                    description=preview[:120] or log.shop_domain,
                    timestamp=_format_activity_time(log.received_at),
                    type=event_type,
                )
            )
        return items

    async def get_app_modules(self, db: Session, user: User) -> list[AppModule]:
        has_store = (
            db.scalar(
                select(func.count()).select_from(Store).where(Store.owner_id == user.id)
            )
            or 0
        ) > 0
        has_store_gmail = (
            db.scalar(
                select(func.count())
                .select_from(GmailStoreLink)
                .join(Store, Store.id == GmailStoreLink.store_id)
                .join(GmailAccount, GmailAccount.id == GmailStoreLink.gmail_account_id)
                .where(
                    Store.owner_id == user.id,
                    GmailAccount.owner_id == user.id,
                    GmailAccount.status == GmailAccountStatus.CONNECTED.value,
                )
            )
            or 0
        ) > 0

        return [
            AppModule(
                id="mod-ai-email",
                name="AI Email Assistant",
                description="Per-store Gmail auto-replies powered by OpenAI with your business rules.",
                slug="ai-email",
                status="active" if has_store_gmail else "setup",
                icon="sparkles",
            ),
            AppModule(
                id="mod-tracking",
                name="Tracking System",
                description="Shipment tracking, branded pages, and carrier enrichment.",
                slug="tracking",
                status="active" if has_store else "setup",
                icon="package",
            ),
            AppModule(
                id="mod-email",
                name="Email Automation",
                description="Shopify-triggered transactional email from each store's Gmail.",
                slug="email",
                status="active" if has_store_gmail else "setup",
                icon="mail",
            ),
            AppModule(
                id="mod-analytics",
                name="Analytics",
                description="Shopify + Meta Ads profitability dashboard with ROAS and net profit.",
                slug="analytics",
                status="active" if has_store else "setup",
                icon="chart",
            ),
            AppModule(
                id="mod-ads",
                name="Ads",
                description="Live Meta ads dashboard with creative health, MER, and AI reports.",
                slug="ads",
                status="active" if has_store else "setup",
                icon="megaphone",
            ),
            AppModule(
                id="mod-ai-ads",
                name="AI Ads",
                description="Creative intelligence engine: learn from Meta ads, then generate new image and video concepts.",
                slug="ai-ads",
                status="active" if has_store else "setup",
                icon="wand",
            ),
            AppModule(
                id="mod-meta-capi",
                name="Server-Side Tracking",
                description="Shopify orders → Meta Conversions API (Purchase) with Pixel dedup.",
                slug="meta-capi",
                status="active" if has_store else "setup",
                icon="radar",
            ),
            AppModule(
                id="mod-md-cleaner",
                name="MD Cleaner",
                description="Strip AI metadata and Content Credentials from pictures before uploading to Meta.",
                slug="md-cleaner",
                status="active",
                icon="eraser",
            ),
            AppModule(
                id="mod-sms",
                name="SMS Notifications",
                description="Order updates and marketing via SMS.",
                slug="sms",
                status="coming_soon",
                icon="message",
            ),
            AppModule(
                id="mod-support",
                name="Customer Support Automation",
                description="Ticket routing, macros, and AI-assisted replies.",
                slug="support",
                status="coming_soon",
                icon="headphones",
            ),
        ]
