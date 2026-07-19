from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AIEmailAssistantSettings,
    EmailAutomationRule,
    EmailSendLog,
    EmailSendStatus,
    GmailAccount,
    GmailAccountStatus,
    InboxEmail,
    InboxEmailStatus,
    OrderTracking,
    Store,
    StoreStatus,
    User,
    WebhookLog,
)


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


class DashboardOverviewResponse(BaseModel):
    metrics: list[OverviewMetric]
    setup_steps: list[SetupStep]
    highlights: list[ModuleHighlight]


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
        "app/uninstalled": ("Store disconnected", "store"),
    }
    return mapping.get(topic, (topic.replace("/", " ").title(), "system"))


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
        has_store = stores_connected > 0
        has_gmail = gmail_connected > 0

        orders_synced = 0
        orders_with_tracking = 0
        emails_sent_week = 0
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
            emails_sent_week = (
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

        inbox_q = select(func.count()).select_from(InboxEmail).where(
            InboxEmail.user_id == user.id,
            InboxEmail.status.in_(
                [InboxEmailStatus.NEW.value, InboxEmailStatus.DRAFT_PENDING.value]
            ),
        )
        if store_id:
            inbox_q = inbox_q.where(InboxEmail.store_id == store_id)
        inbox_needs_attention = db.scalar(inbox_q) or 0

        ai_settings = db.scalar(
            select(AIEmailAssistantSettings).where(AIEmailAssistantSettings.user_id == user.id)
        )
        ai_automation_on = bool(ai_settings and ai_settings.automation_enabled)

        tracking_hint = (
            "Connect a Shopify store to sync orders"
            if not has_store
            else "No orders synced yet"
            if orders_synced == 0
            else f"{orders_with_tracking} with tracking numbers"
        )
        email_hint = (
            "Connect Gmail for automations"
            if not has_gmail
            else "No sends this week"
            if emails_sent_week == 0
            else "Transactional emails (7 days)"
        )

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

        highlights: list[ModuleHighlight] = [
            ModuleHighlight(
                slug="ai-email",
                name="AI Email Assistant",
                status="active" if has_gmail else "setup",
                stat_label="Inbox to review",
                stat_value=str(inbox_needs_attention),
                hint=(
                    "Autopilot on"
                    if ai_automation_on
                    else "Connect Gmail to enable"
                    if not has_gmail
                    else "Autopilot off — open to configure"
                ),
            ),
            ModuleHighlight(
                slug="tracking",
                name="Tracking",
                status="active" if has_store else "setup",
                stat_label="Orders synced",
                stat_value=str(orders_synced),
                hint=tracking_hint,
            ),
            ModuleHighlight(
                slug="email",
                name="Email Automation",
                status="active" if has_gmail else "setup",
                stat_label="Active rules",
                stat_value=str(automation_rules_on),
                hint=(
                    "Connect Gmail to create flows"
                    if not has_gmail
                    else "No rules enabled yet"
                    if automation_rules_on == 0
                    else "Shopify event triggers"
                ),
            ),
        ]

        return DashboardOverviewResponse(
            metrics=metrics,
            setup_steps=setup_steps,
            highlights=highlights,
        )

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
            preview = (log.payload_preview or "")[:120]
            items.append(
                ActivityItem(
                    id=log.id,
                    title=title,
                    description=preview or log.shop_domain,
                    timestamp=_format_activity_time(log.received_at),
                    type=event_type,
                )
            )
        return items

    async def get_app_modules(self, db: Session, user: User) -> list[AppModule]:
        has_store = (
            db.scalar(
                select(func.count())
                .select_from(Store)
                .where(Store.owner_id == user.id, Store.status == StoreStatus.CONNECTED.value)
            )
            or 0
        ) > 0
        has_gmail = (
            db.scalar(
                select(func.count())
                .select_from(GmailAccount)
                .where(
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
                description="Gmail auto-replies powered by OpenAI with your business rules.",
                slug="ai-email",
                status="active" if has_gmail else "setup",
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
                description="Shopify-triggered transactional email from Gmail.",
                slug="email",
                status="active" if has_gmail else "setup",
                icon="mail",
            ),
            AppModule(
                id="mod-analytics",
                name="Analytics",
                description="Revenue, engagement, and automation performance.",
                slug="analytics",
                status="coming_soon",
                icon="chart",
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
