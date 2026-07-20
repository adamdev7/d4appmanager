from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


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


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_user_email_settings_constraints()
    _migrate_ai_email_assistant_columns()
    _migrate_user_openai_key_columns()
    _migrate_order_tracking_summary_columns()
    _migrate_email_branding_columns()
