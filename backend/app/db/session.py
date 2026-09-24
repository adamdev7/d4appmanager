import logging
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_dir() -> None:
    if settings.database_url.startswith("sqlite"):
        path = settings.database_url.replace("sqlite:///", "")
        Path(path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_user_email_settings_constraints() -> None:
    """Allow per-store email settings (user_id + store_id), not one row per user only."""
    insp = inspect(engine)
    if "user_email_settings" not in insp.get_table_names():
        return

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE user_email_settings "
                    "DROP CONSTRAINT IF EXISTS user_email_settings_user_id_key"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE user_email_settings "
                    "DROP CONSTRAINT IF EXISTS uq_user_email_settings_user_store"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE user_email_settings "
                    "ADD CONSTRAINT uq_user_email_settings_user_store "
                    "UNIQUE (user_id, store_id)"
                )
            )


def _migrate_ai_email_assistant_columns() -> None:
    """Add reply-filter columns to existing SQLite/Postgres installs."""
    insp = inspect(engine)
    if "ai_email_assistant_settings" not in insp.get_table_names():
        return

    settings_cols = {c["name"] for c in insp.get_columns("ai_email_assistant_settings")}
    inbox_cols = {c["name"] for c in insp.get_columns("inbox_emails")} if "inbox_emails" in insp.get_table_names() else set()

    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            if "email_filter_enabled" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN email_filter_enabled BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "filter_automated_emails" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN filter_automated_emails BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "filter_non_business_emails" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN filter_non_business_emails BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "filter_custom_rules" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN filter_custom_rules TEXT DEFAULT '' NOT NULL"
                    )
                )
            if "automation_enabled" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN automation_enabled BOOLEAN DEFAULT 0 NOT NULL"
                    )
                )
            if "automation_interval_minutes" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN automation_interval_minutes INTEGER DEFAULT 15 NOT NULL"
                    )
                )
            if "automation_max_emails_per_run" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN automation_max_emails_per_run INTEGER DEFAULT 10 NOT NULL"
                    )
                )
            if "automation_last_run_at" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN automation_last_run_at DATETIME"
                    )
                )
            if "automation_last_error" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN automation_last_error TEXT"
                    )
                )
            if "one_reply_per_thread" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN one_reply_per_thread BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "sync_only_customer_unread" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN sync_only_customer_unread BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "verify_gmail_thread_before_reply" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN verify_gmail_thread_before_reply BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "use_thread_context" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN use_thread_context BOOLEAN DEFAULT 1 NOT NULL"
                    )
                )
            if "full_scan_status" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_status VARCHAR(32) DEFAULT 'idle' NOT NULL"
                    )
                )
            if "full_scan_message" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_message TEXT DEFAULT '' NOT NULL"
                    )
                )
            if "full_scan_progress" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_progress INTEGER DEFAULT 0 NOT NULL"
                    )
                )
            if "full_scan_total" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_total INTEGER DEFAULT 0 NOT NULL"
                    )
                )
            if "full_scan_started_at" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_started_at DATETIME"
                    )
                )
            if "full_scan_finished_at" not in settings_cols:
                conn.execute(
                    text(
                        "ALTER TABLE ai_email_assistant_settings "
                        "ADD COLUMN full_scan_finished_at DATETIME"
                    )
                )
            if "skip_reason" not in inbox_cols and inbox_cols:
                conn.execute(text("ALTER TABLE inbox_emails ADD COLUMN skip_reason TEXT"))
            if "filter_category" not in inbox_cols and inbox_cols:
                conn.execute(text("ALTER TABLE inbox_emails ADD COLUMN filter_category VARCHAR(32)"))
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS email_filter_enabled BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS filter_automated_emails BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS filter_non_business_emails BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS filter_custom_rules TEXT DEFAULT '' NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS automation_enabled BOOLEAN DEFAULT FALSE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS automation_interval_minutes INTEGER DEFAULT 15 NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS automation_max_emails_per_run INTEGER DEFAULT 10 NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS automation_last_run_at TIMESTAMPTZ"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS automation_last_error TEXT"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS one_reply_per_thread BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS sync_only_customer_unread BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS verify_gmail_thread_before_reply BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS use_thread_context BOOLEAN DEFAULT TRUE NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_status VARCHAR(32) DEFAULT 'idle' NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_message TEXT DEFAULT '' NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_progress INTEGER DEFAULT 0 NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_total INTEGER DEFAULT 0 NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_started_at TIMESTAMPTZ"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE ai_email_assistant_settings "
                    "ADD COLUMN IF NOT EXISTS full_scan_finished_at TIMESTAMPTZ"
                )
            )
            if inbox_cols:
                conn.execute(
                    text("ALTER TABLE inbox_emails ADD COLUMN IF NOT EXISTS skip_reason TEXT")
                )
                conn.execute(
                    text(
                        "ALTER TABLE inbox_emails ADD COLUMN IF NOT EXISTS filter_category VARCHAR(32)"
                    )
                )


def _migrate_user_openai_key_columns() -> None:
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return

    user_cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            if "openai_api_key_encrypted" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN openai_api_key_encrypted TEXT"))
            if "openai_api_key_hint" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN openai_api_key_hint VARCHAR(8)"))
        elif dialect == "postgresql":
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS openai_api_key_encrypted TEXT")
            )
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS openai_api_key_hint VARCHAR(8)")
            )


def _migrate_user_general_prefs() -> None:
    """Profile notification toggles on General settings."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return

    user_cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            if "email_notifications" not in user_cols:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN email_notifications BOOLEAN DEFAULT 1")
                )
            if "weekly_digest" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN weekly_digest BOOLEAN DEFAULT 0"))
        elif dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_notifications "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS weekly_digest "
                    "BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )


def _migrate_module_openai_keys() -> None:
    """Copy legacy user OpenAI keys into independent per-module rows once.

    If a user already has any module row, they have been migrated — do not
    recreate Ads/AI Ads keys after the user disconnects those modules.
    """
    from app.db.models import User, UserModuleOpenAIKey

    insp = inspect(engine)
    if "users" not in insp.get_table_names() or "user_module_openai_keys" not in insp.get_table_names():
        return

    db = SessionLocal()
    try:
        users = db.scalars(select(User).where(User.openai_api_key_encrypted.isnot(None))).all()
        all_modules = ("ai-email", "ai-ads", "ads")
        for user in users:
            has_any = db.scalar(
                select(UserModuleOpenAIKey.id).where(UserModuleOpenAIKey.user_id == user.id)
            )
            seed_modules = all_modules if not has_any else ("ai-email",)
            for module in seed_modules:
                exists = db.scalar(
                    select(UserModuleOpenAIKey.id).where(
                        UserModuleOpenAIKey.user_id == user.id,
                        UserModuleOpenAIKey.module_slug == module,
                    )
                )
                if exists:
                    continue
                db.add(
                    UserModuleOpenAIKey(
                        user_id=user.id,
                        module_slug=module,
                        api_key_encrypted=user.openai_api_key_encrypted,
                        api_key_hint=user.openai_api_key_hint,
                    )
                )
        db.commit()
    finally:
        db.close()


def _migrate_order_tracking_summary_columns() -> None:
    insp = inspect(engine)
    if "order_tracking" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("order_tracking")}
    with engine.begin() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            if "order_placed_at" not in cols:
                conn.execute(text("ALTER TABLE order_tracking ADD COLUMN order_placed_at DATETIME"))
            if "order_total_display" not in cols:
                conn.execute(text("ALTER TABLE order_tracking ADD COLUMN order_total_display VARCHAR(32)"))
            if "order_currency" not in cols:
                conn.execute(text("ALTER TABLE order_tracking ADD COLUMN order_currency VARCHAR(8)"))
            if "line_items_json" not in cols:
                conn.execute(
                    text("ALTER TABLE order_tracking ADD COLUMN line_items_json TEXT DEFAULT '[]' NOT NULL")
                )
            if "fulfillments_json" not in cols:
                conn.execute(
                    text("ALTER TABLE order_tracking ADD COLUMN fulfillments_json TEXT DEFAULT '[]' NOT NULL")
                )
            if "shopify_financial_status" not in cols:
                conn.execute(
                    text("ALTER TABLE order_tracking ADD COLUMN shopify_financial_status VARCHAR(32)")
                )
            if "shopify_fulfillment_status" not in cols:
                conn.execute(
                    text("ALTER TABLE order_tracking ADD COLUMN shopify_fulfillment_status VARCHAR(32)")
                )
            if "customer_name" not in cols:
                conn.execute(text("ALTER TABLE order_tracking ADD COLUMN customer_name VARCHAR(255)"))
        elif dialect == "postgresql":
            conn.execute(
                text("ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS order_placed_at TIMESTAMPTZ")
            )
            conn.execute(
                text(
                    "ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS order_total_display VARCHAR(32)"
                )
            )
            conn.execute(
                text("ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS order_currency VARCHAR(8)")
            )
            conn.execute(
                text(
                    "ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS line_items_json TEXT DEFAULT '[]' NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS fulfillments_json TEXT DEFAULT '[]' NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS shopify_financial_status VARCHAR(32)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS shopify_fulfillment_status VARCHAR(32)"
                )
            )
            conn.execute(
                text("ALTER TABLE order_tracking ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255)")
            )


def _migrate_email_branding_columns() -> None:
    """Add store branding + template layout columns for email automation."""
    insp = inspect(engine)
    dialect = engine.dialect.name

    if "stores" in insp.get_table_names():
        store_cols = {c["name"] for c in insp.get_columns("stores")}
        with engine.begin() as conn:
            if dialect == "sqlite":
                if "email_theme_color" not in store_cols:
                    conn.execute(
                        text("ALTER TABLE stores ADD COLUMN email_theme_color VARCHAR(32) DEFAULT '#0d9488'")
                    )
                if "email_logo_path" not in store_cols:
                    conn.execute(text("ALTER TABLE stores ADD COLUMN email_logo_path VARCHAR(512)"))
            elif dialect == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS "
                        "email_theme_color VARCHAR(32) DEFAULT '#0d9488'"
                    )
                )
                conn.execute(
                    text("ALTER TABLE stores ADD COLUMN IF NOT EXISTS email_logo_path VARCHAR(512)")
                )

    if "email_templates" in insp.get_table_names():
        tmpl_cols = {c["name"] for c in insp.get_columns("email_templates")}
        with engine.begin() as conn:
            if dialect == "sqlite":
                if "layout_preset" not in tmpl_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE email_templates "
                            "ADD COLUMN layout_preset VARCHAR(32) DEFAULT 'classic'"
                        )
                    )
            elif dialect == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE email_templates "
                        "ADD COLUMN IF NOT EXISTS layout_preset VARCHAR(32) DEFAULT 'classic'"
                    )
                )


def _migrate_analytics_balance_columns() -> None:
    """Add prior-site revenue + analytics start date for Shopify migrations."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    table = "store_analytics_settings"
    if table not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(table)}
    additions: list[tuple[str, str]] = [
        ("analytics_start_date", "VARCHAR(10)"),
        ("prior_external_revenue", "VARCHAR(16) DEFAULT '0'"),
        ("prior_external_costs", "VARCHAR(16) DEFAULT '0'"),
        ("prior_external_label", "VARCHAR(64) DEFAULT 'Prior site (Stripe)'"),
    ]
    with engine.begin() as conn:
        for name, col_type in additions:
            if name in cols:
                continue
            if dialect == "sqlite":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
            elif dialect == "postgresql":
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                )


def _migrate_analytics_mrr_columns() -> None:
    """Add opt-in MRR analytics columns (Phoenix / multi-Stripe subscriptions)."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    table = "store_analytics_settings"
    if table not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(table)}
    additions: list[tuple[str, str]] = [
        ("mrr_enabled", "BOOLEAN DEFAULT 0" if dialect == "sqlite" else "BOOLEAN DEFAULT FALSE"),
        ("mrr_source", "VARCHAR(32) DEFAULT 'manual'"),
        ("mrr_manual_amount", "VARCHAR(16) DEFAULT '0'"),
        ("mrr_manual_subscribers", "INTEGER DEFAULT 0"),
        ("mrr_manual_churn_pct", "VARCHAR(8) DEFAULT '0'"),
        ("mrr_currency", "VARCHAR(8)"),
        ("display_currency", "VARCHAR(8)"),
        ("mrr_webhook_secret_encrypted", "TEXT"),
        ("mrr_webhook_secret_hint", "VARCHAR(8)"),
        ("mrr_last_synced_at", "TIMESTAMP" if dialect == "sqlite" else "TIMESTAMPTZ"),
    ]
    with engine.begin() as conn:
        for name, col_type in additions:
            if name in cols:
                continue
            if dialect == "sqlite":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
            elif dialect == "postgresql":
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                )

        # Clear invented fee defaults users never intentionally set
        conn.execute(
            text(
                "UPDATE store_analytics_settings SET transaction_fee_percent = '0' "
                "WHERE transaction_fee_percent IN ('2.9', '2.90')"
            )
        )
        conn.execute(
            text(
                "UPDATE store_analytics_settings SET transaction_fee_fixed = '0' "
                "WHERE transaction_fee_fixed IN ('0.30', '0.3')"
            )
        )


def _migrate_sync_delivered_to_shopify_column() -> None:
    """Add toggle to push carrier-delivered status back to Shopify fulfillments."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    table = "store_tracking_settings"
    if table not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(table)}
    if "sync_delivered_to_shopify" in cols:
        return

    col_type = (
        "BOOLEAN DEFAULT 1" if dialect == "sqlite" else "BOOLEAN DEFAULT TRUE"
    )
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN sync_delivered_to_shopify {col_type}")
            )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN IF NOT EXISTS sync_delivered_to_shopify {col_type}"
                )
            )


def _migrate_verification_code_attempts() -> None:
    """Track failed OTP guesses so codes can be locked after too many attempts."""
    insp = inspect(engine)
    table = "verification_codes"
    if table not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(table)}
    if "attempt_count" in cols:
        return

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN attempt_count INTEGER DEFAULT 0 NOT NULL")
            )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    f"ALTER TABLE {table} "
                    "ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0 NOT NULL"
                )
            )


def _migrate_ai_email_null_store_scope() -> None:
    """Attach legacy user-wide AI settings/inbox rows to each user's first store."""
    insp = inspect(engine)
    if "ai_email_assistant_settings" not in insp.get_table_names():
        return
    if "stores" not in insp.get_table_names():
        return

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            # Drop orphan user-wide settings when a store-scoped row already exists
            conn.execute(
                text(
                    """
                    DELETE FROM ai_email_assistant_settings
                    WHERE store_id IS NULL
                      AND EXISTS (
                        SELECT 1 FROM ai_email_assistant_settings a2
                        WHERE a2.user_id = ai_email_assistant_settings.user_id
                          AND a2.store_id IS NOT NULL
                      )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE ai_email_assistant_settings
                    SET store_id = (
                        SELECT s.id FROM stores s
                        WHERE s.owner_id = ai_email_assistant_settings.user_id
                        ORDER BY s.created_at ASC
                        LIMIT 1
                    )
                    WHERE store_id IS NULL
                      AND EXISTS (
                        SELECT 1 FROM stores s
                        WHERE s.owner_id = ai_email_assistant_settings.user_id
                      )
                      AND NOT EXISTS (
                        SELECT 1 FROM ai_email_assistant_settings a2
                        WHERE a2.user_id = ai_email_assistant_settings.user_id
                          AND a2.store_id = (
                            SELECT s.id FROM stores s
                            WHERE s.owner_id = ai_email_assistant_settings.user_id
                            ORDER BY s.created_at ASC
                            LIMIT 1
                          )
                      )
                    """
                )
            )
            if "inbox_emails" in insp.get_table_names():
                conn.execute(
                    text(
                        """
                        UPDATE inbox_emails
                        SET store_id = (
                            SELECT s.id FROM stores s
                            WHERE s.owner_id = inbox_emails.user_id
                            ORDER BY s.created_at ASC
                            LIMIT 1
                        )
                        WHERE store_id IS NULL
                          AND EXISTS (
                            SELECT 1 FROM stores s
                            WHERE s.owner_id = inbox_emails.user_id
                          )
                        """
                    )
                )
        elif dialect == "postgresql":
            conn.execute(
                text(
                    """
                    DELETE FROM ai_email_assistant_settings a
                    WHERE a.store_id IS NULL
                      AND EXISTS (
                        SELECT 1 FROM ai_email_assistant_settings a2
                        WHERE a2.user_id = a.user_id
                          AND a2.store_id IS NOT NULL
                      )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE ai_email_assistant_settings AS a
                    SET store_id = s.id
                    FROM (
                        SELECT DISTINCT ON (owner_id) id, owner_id
                        FROM stores
                        ORDER BY owner_id, created_at ASC
                    ) AS s
                    WHERE a.store_id IS NULL
                      AND a.user_id = s.owner_id
                      AND NOT EXISTS (
                        SELECT 1 FROM ai_email_assistant_settings a2
                        WHERE a2.user_id = a.user_id
                          AND a2.store_id = s.id
                      )
                    """
                )
            )
            if "inbox_emails" in insp.get_table_names():
                conn.execute(
                    text(
                        """
                        UPDATE inbox_emails AS i
                        SET store_id = s.id
                        FROM (
                            SELECT DISTINCT ON (owner_id) id, owner_id
                            FROM stores
                            ORDER BY owner_id, created_at ASC
                        ) AS s
                        WHERE i.store_id IS NULL
                          AND i.user_id = s.owner_id
                        """
                    )
                )


def _migrate_meta_capi_enrichment_columns() -> None:
    """Add InitiateCheckout + browser beacon settings for Meta CAPI."""
    insp = inspect(engine)
    table = "store_meta_capi_settings"
    if table not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns(table)}
    dialect = engine.dialect.name
    additions: list[tuple[str, str]] = [
        (
            "send_initiate_checkout",
            "BOOLEAN DEFAULT 1" if dialect == "sqlite" else "BOOLEAN DEFAULT TRUE",
        ),
        ("browser_event_token", "VARCHAR(64)"),
    ]
    with engine.begin() as conn:
        for name, col_type in additions:
            if name in cols:
                continue
            if dialect == "sqlite":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
            elif dialect == "postgresql":
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                )


def _migrate_ai_ads_job_progress_columns() -> None:
    """Live generation progress log for the AI Ads studio."""
    insp = inspect(engine)
    table = "ai_ads_generation_jobs"
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    dialect = engine.dialect.name
    additions: list[tuple[str, str]] = [
        ("progress_step", "VARCHAR(32) DEFAULT ''"),
        ("progress_pct", "INTEGER DEFAULT 0"),
        ("progress_log_json", "TEXT DEFAULT '[]'"),
    ]
    with engine.begin() as conn:
        for name, col_type in additions:
            if name in cols:
                continue
            if dialect == "sqlite":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
            elif dialect == "postgresql":
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                )


def _migrate_ai_ads_catalog_columns() -> None:
    """Product photo cache timestamps on AI Ads settings."""
    insp = inspect(engine)
    table = "store_ai_ads_settings"
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if "last_product_catalog_at" in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN last_product_catalog_at DATETIME"))
        elif dialect == "postgresql":
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS last_product_catalog_at TIMESTAMPTZ")
            )


def _migrate_ai_ads_catalog_photo_bytes() -> None:
    """Durable product photo bytes. Instances do not share a filesystem, so local_path alone
    leaves rows pointing at files that only exist on the machine that downloaded them."""
    insp = inspect(engine)
    table = "ai_ads_shopify_product_images"
    if table not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns(table)}
    if "image_bytes" in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN image_bytes BLOB"))
        elif dialect == "postgresql":
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS image_bytes BYTEA"))


def _migrate_ai_ads_owner_columns() -> None:
    """Tie generated creatives (including video specs) to the account that created them."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    for table in ("ai_ads_creative_assets", "ai_ads_concepts"):
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "user_id" in cols:
            continue
        with engine.begin() as conn:
            if dialect == "sqlite":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(36)"))
            elif dialect == "postgresql":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"))
    names = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        if "ai_ads_creative_assets" in names:
            conn.execute(
                text(
                    """
                    UPDATE ai_ads_creative_assets
                    SET user_id = (
                        SELECT j.user_id FROM ai_ads_generation_jobs j
                        WHERE j.id = ai_ads_creative_assets.job_id
                    )
                    WHERE user_id IS NULL AND job_id IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE ai_ads_creative_assets
                    SET user_id = (
                        SELECT s.owner_id FROM stores s
                        WHERE s.id = ai_ads_creative_assets.store_id
                    )
                    WHERE user_id IS NULL
                    """
                )
            )
        if "ai_ads_concepts" in names:
            conn.execute(
                text(
                    """
                    UPDATE ai_ads_concepts
                    SET user_id = (
                        SELECT j.user_id FROM ai_ads_generation_jobs j
                        WHERE j.id = ai_ads_concepts.job_id
                    )
                    WHERE user_id IS NULL AND job_id IS NOT NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE ai_ads_concepts
                    SET user_id = (
                        SELECT s.owner_id FROM stores s
                        WHERE s.id = ai_ads_concepts.store_id
                    )
                    WHERE user_id IS NULL
                    """
                )
            )


def _migrate_ai_email_order_tracking_columns() -> None:
    """Order-aware replies: order context toggle + the tracking button on each reply."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    names = set(insp.get_table_names())

    tables: dict[str, list[tuple[str, str]]] = {
        "ai_email_assistant_settings": [
            ("use_order_context", "BOOLEAN DEFAULT 1" if dialect == "sqlite" else "BOOLEAN DEFAULT TRUE"),
            (
                "tracking_button_enabled",
                "BOOLEAN DEFAULT 1" if dialect == "sqlite" else "BOOLEAN DEFAULT TRUE",
            ),
            ("tracking_page_url", "VARCHAR(512) DEFAULT ''"),
        ],
        "ai_email_replies": [
            ("tracking_url", "TEXT"),
            ("tracking_order_number", "VARCHAR(64)"),
            ("tracking_number", "VARCHAR(128)"),
            ("tracking_carrier", "VARCHAR(128)"),
        ],
    }

    for table, additions in tables.items():
        if table not in names:
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        with engine.begin() as conn:
            for name, col_type in additions:
                if name in cols:
                    continue
                if dialect == "sqlite":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
                elif dialect == "postgresql":
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                    )


def _migrate_shared_whatsapp_connection() -> None:
    """User-level CallMeBot connection(s) + module on/off flags.

    Phone and API key live only on user_whatsapp_settings. Email Assistant and
    AI Ads store booleans. Leftover keys on ai_email_assistant_settings (if any)
    are copied once so setup does not have to be repeated.
    """
    from app.db.models import UserWhatsAppSettings

    try:
        UserWhatsAppSettings.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        logger.exception("Could not create user_whatsapp_settings")

    _migrate_whatsapp_multi_connections()

    insp = inspect(engine)
    try:
        insp.clear_cache()
    except Exception:
        pass
    dialect = engine.dialect.name
    names = set(insp.get_table_names())

    def _add_bool(table: str, column: str) -> None:
        if table not in names:
            return
        cols = {c["name"] for c in insp.get_columns(table)}
        if column in cols:
            return
        col_type = "BOOLEAN DEFAULT 0" if dialect == "sqlite" else "BOOLEAN DEFAULT FALSE"
        try:
            with engine.begin() as conn:
                if dialect == "sqlite":
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                elif dialect == "postgresql":
                    conn.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                        )
                    )
        except Exception:
            logger.exception("Could not add %s.%s", table, column)

    _add_bool("ai_email_assistant_settings", "whatsapp_alerts_enabled")
    _add_bool("store_ai_ads_settings", "whatsapp_weekly_alerts_enabled")

    try:
        insp.clear_cache()
    except Exception:
        pass
    names = set(insp.get_table_names())
    if "user_whatsapp_settings" not in names or "ai_email_assistant_settings" not in names:
        return
    email_cols = {c["name"] for c in insp.get_columns("ai_email_assistant_settings")}
    if "whatsapp_api_key_encrypted" not in email_cols:
        return

    db = SessionLocal()
    try:
        existing = {
            row.user_id
            for row in db.scalars(select(UserWhatsAppSettings)).all()
            if row.api_key_encrypted
        }
        legacy_rows = db.execute(
            text(
                """
                SELECT user_id, whatsapp_phone, whatsapp_api_key_encrypted,
                       whatsapp_api_key_hint, whatsapp_last_error
                FROM ai_email_assistant_settings
                WHERE whatsapp_api_key_encrypted IS NOT NULL
                """
            )
        ).mappings().all()
        for legacy in legacy_rows:
            uid = legacy["user_id"]
            if uid in existing:
                continue
            row = db.scalar(
                select(UserWhatsAppSettings).where(UserWhatsAppSettings.user_id == uid)
            )
            if not row:
                row = UserWhatsAppSettings(user_id=uid)
                db.add(row)
            if row.api_key_encrypted:
                existing.add(uid)
                continue
            row.phone = legacy["whatsapp_phone"] or ""
            row.api_key_encrypted = legacy["whatsapp_api_key_encrypted"]
            row.api_key_hint = legacy["whatsapp_api_key_hint"]
            row.last_error = legacy["whatsapp_last_error"]
            existing.add(uid)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("WhatsApp legacy key copy failed")
    finally:
        db.close()


def _migrate_whatsapp_multi_connections() -> None:
    """Allow several CallMeBot numbers per user (drop one-row-per-user unique)."""
    insp = inspect(engine)
    if "user_whatsapp_settings" not in insp.get_table_names():
        return
    dialect = engine.dialect.name
    cols = {c["name"] for c in insp.get_columns("user_whatsapp_settings")}

    with engine.begin() as conn:
        if "label" not in cols:
            try:
                if dialect == "sqlite":
                    conn.execute(
                        text(
                            "ALTER TABLE user_whatsapp_settings "
                            "ADD COLUMN label VARCHAR(64) DEFAULT ''"
                        )
                    )
                elif dialect == "postgresql":
                    conn.execute(
                        text(
                            "ALTER TABLE user_whatsapp_settings "
                            "ADD COLUMN IF NOT EXISTS label VARCHAR(64) DEFAULT ''"
                        )
                    )
            except Exception:
                logger.exception("Could not add user_whatsapp_settings.label")

        if dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE user_whatsapp_settings "
                    "DROP CONSTRAINT IF EXISTS uq_user_whatsapp_settings_user"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE user_whatsapp_settings "
                    "DROP CONSTRAINT IF EXISTS user_whatsapp_settings_user_id_key"
                )
            )
            try:
                conn.execute(
                    text(
                        "ALTER TABLE user_whatsapp_settings "
                        "ADD CONSTRAINT uq_user_whatsapp_settings_user_phone "
                        "UNIQUE (user_id, phone)"
                    )
                )
            except Exception:
                # Already exists or phones empty — fine.
                pass
            return

        if dialect != "sqlite":
            return

        # SQLite: rebuild if the old one-row-per-user unique is still present.
        index_rows = conn.execute(text("PRAGMA index_list('user_whatsapp_settings')")).fetchall()
        needs_rebuild = False
        for row in index_rows:
            # row: (seq, name, unique, origin, partial)
            name = row[1]
            is_unique = bool(row[2])
            if not is_unique:
                continue
            cols_info = conn.execute(text(f"PRAGMA index_info('{name}')")).fetchall()
            col_names = [c[2] for c in cols_info]
            if col_names == ["user_id"]:
                needs_rebuild = True
                break
        if not needs_rebuild:
            return

        conn.execute(
            text(
                """
                CREATE TABLE user_whatsapp_settings_new (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL,
                    label VARCHAR(64) DEFAULT '',
                    phone VARCHAR(32) DEFAULT '',
                    api_key_encrypted TEXT,
                    api_key_hint VARCHAR(16),
                    last_error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, phone),
                    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
                )
                """
            )
        )
        has_label = "label" in {c["name"] for c in insp.get_columns("user_whatsapp_settings")}
        if has_label:
            conn.execute(
                text(
                    """
                    INSERT INTO user_whatsapp_settings_new
                    (id, user_id, label, phone, api_key_encrypted, api_key_hint,
                     last_error, created_at, updated_at)
                    SELECT id, user_id, COALESCE(label, ''), phone, api_key_encrypted,
                           api_key_hint, last_error, created_at, updated_at
                    FROM user_whatsapp_settings
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO user_whatsapp_settings_new
                    (id, user_id, label, phone, api_key_encrypted, api_key_hint,
                     last_error, created_at, updated_at)
                    SELECT id, user_id, '', phone, api_key_encrypted,
                           api_key_hint, last_error, created_at, updated_at
                    FROM user_whatsapp_settings
                    """
                )
            )
        conn.execute(text("DROP TABLE user_whatsapp_settings"))
        conn.execute(
            text("ALTER TABLE user_whatsapp_settings_new RENAME TO user_whatsapp_settings")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_whatsapp_settings_user_id "
                "ON user_whatsapp_settings (user_id)"
            )
        )

def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_user_email_settings_constraints()
    _migrate_ai_email_assistant_columns()
    _migrate_ai_email_order_tracking_columns()
    _migrate_user_openai_key_columns()
    _migrate_user_general_prefs()
    _migrate_module_openai_keys()
    _migrate_order_tracking_summary_columns()
    _migrate_email_branding_columns()
    _migrate_analytics_balance_columns()
    _migrate_analytics_mrr_columns()
    _migrate_sync_delivered_to_shopify_column()
    _migrate_verification_code_attempts()
    _migrate_ai_email_null_store_scope()
    _migrate_meta_capi_enrichment_columns()
    _migrate_ai_ads_job_progress_columns()
    _migrate_ai_ads_owner_columns()
    _migrate_ai_ads_catalog_columns()
    _migrate_ai_ads_catalog_photo_bytes()
    _migrate_shared_whatsapp_connection()
