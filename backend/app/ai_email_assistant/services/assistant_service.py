import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai_email_assistant.ai_service import AIService
from app.ai_email_assistant.automation_control import stop_autopilot
from app.ai_email_assistant.duplicate_guard import (
    ALREADY_REPLIED_REASON,
    GENERATING_MODEL_MARKER,
    find_active_draft,
    find_sent_reply,
    mark_thread_siblings_handled,
    thread_has_answered_in_db,
    thread_has_sent_reply,
)
from app.ai_email_assistant.email_filter import config_from_settings, evaluate_email_filter
from app.ai_email_assistant.thread_context import format_customer_relationship
from app.ai_email_assistant.order_link import extract_order_numbers
from app.ai_email_assistant.openai_errors import OpenAIServiceError, openai_error_from_exception
from app.ai_email_assistant.prompt_builder import BusinessContext
from app.config import settings
from app.core.openai_credentials import (
    clear_user_openai_api_key,
    is_openai_configured,
    openai_key_status,
    resolve_openai_api_key,
    set_user_openai_api_key,
)
from app.db.models import (
    AIEmailAssistantSettings,
    AIEmailReply,
    AIReplyStatus,
    GmailAccount,
    GmailAccountStatus,
    GmailStoreLink,
    InboxEmail,
    InboxEmailStatus,
    OrderTracking,
    Store,
    StoreStatus,
    User,
)
from app.integrations.gmail.inbox_client import GmailInboxClient
from app.models.ai_email_assistant import (
    AIEmailAssistantSettingsResponse,
    AIEmailAssistantSettingsUpdate,
    AIEmailAssistantStatsResponse,
    AIReplyLogEntry,
    AIReplyResponse,
    FullHistoryScanResponse,
    InboxEmailResponse,
    InboxThreadResponse,
    NamedCount,
    OpenAIKeyStatusResponse,
    PeriodStats,
    RelatedOrderItem,
    RelatedOrdersResponse,
    SetOpenAIKeyBody,
    ThreadMessageResponse,
)
from app.services.tracking_service import TrackingService
from app.tracking.payload_parser import normalize_email, normalize_order_number, order_number_variants
from app.tracking.track_service import TrackOrderService

logger = logging.getLogger(__name__)


class AIEmailAssistantService:
    def _ensure_store(self, db: Session, user: User, store_id: str | None) -> Store:
        if not store_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select a store for the AI Email Assistant. Settings and inbox are per store.",
            )
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def _gmail_linked_to_store(self, db: Session, *, gmail_account_id: str, store_id: str) -> bool:
        return (
            db.scalar(
                select(GmailStoreLink.id).where(
                    GmailStoreLink.gmail_account_id == gmail_account_id,
                    GmailStoreLink.store_id == store_id,
                )
            )
            is not None
        )

    def resolve_gmail_account_id(
        self, db: Session, user: User, settings_row: AIEmailAssistantSettings
    ) -> str | None:
        """Resolve Gmail for this store only — never fall back to another store's mailbox."""
        store_id = settings_row.store_id
        if not store_id:
            return None

        if settings_row.gmail_account_id:
            acc = db.get(GmailAccount, settings_row.gmail_account_id)
            if (
                acc
                and acc.owner_id == user.id
                and acc.status == GmailAccountStatus.CONNECTED.value
                and self._gmail_linked_to_store(
                    db, gmail_account_id=acc.id, store_id=store_id
                )
            ):
                return acc.id

        linked = db.scalar(
            select(GmailAccount)
            .join(GmailStoreLink, GmailStoreLink.gmail_account_id == GmailAccount.id)
            .where(
                GmailStoreLink.store_id == store_id,
                GmailAccount.owner_id == user.id,
                GmailAccount.status == GmailAccountStatus.CONNECTED.value,
            )
            .order_by(GmailAccount.is_default_sender.desc())
            .limit(1)
        )
        return linked.id if linked else None

    def get_or_create_settings(
        self, db: Session, user: User, store_id: str | None = None
    ) -> AIEmailAssistantSettings:
        store = self._ensure_store(db, user, store_id)
        row = db.scalar(
            select(AIEmailAssistantSettings).where(
                AIEmailAssistantSettings.user_id == user.id,
                AIEmailAssistantSettings.store_id == store.id,
            )
        )
        if not row:
            row = AIEmailAssistantSettings(user_id=user.id, store_id=store.id)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    def _ai_service(self, user: User, settings_row: AIEmailAssistantSettings) -> AIService:
        api_key = resolve_openai_api_key(user)
        if not api_key:
            raise OpenAIServiceError(
                user_message="Add your OpenAI API key in AI Email Assistant settings before using AI features.",
                stop_autopilot=True,
            )
        return AIService(model=settings_row.openai_model, api_key=api_key)

    @staticmethod
    def _http_status_for_ai_error(exc: OpenAIServiceError) -> int:
        if exc.status_code in (401, 402, 403, 429):
            return exc.status_code
        if exc.status_code and exc.status_code >= 500:
            return status.HTTP_502_BAD_GATEWAY
        return status.HTTP_400_BAD_REQUEST

    def get_openai_key_status(self, user: User) -> OpenAIKeyStatusResponse:
        data = openai_key_status(user)
        return OpenAIKeyStatusResponse(**data)

    def save_openai_key(self, db: Session, user: User, body: SetOpenAIKeyBody) -> OpenAIKeyStatusResponse:
        try:
            set_user_openai_api_key(db, user, body.api_key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return self.get_openai_key_status(user)

    def delete_openai_key(self, db: Session, user: User) -> OpenAIKeyStatusResponse:
        clear_user_openai_api_key(db, user)
        return self.get_openai_key_status(user)

    def get_settings_response(
        self, db: Session, user: User, store_id: str | None = None
    ) -> AIEmailAssistantSettingsResponse:
        self._ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, user, store_id)
        key_info = openai_key_status(user)
        return AIEmailAssistantSettingsResponse(
            id=row.id,
            business_name=row.business_name,
            business_type=row.business_type,
            tone_of_voice=row.tone_of_voice,
            rules=row.rules,
            policies=row.policies,
            faq=row.faq,
            auto_send_enabled=row.auto_send_enabled,
            gmail_account_id=row.gmail_account_id,
            openai_model=row.openai_model,
            email_filter_enabled=row.email_filter_enabled,
            filter_automated_emails=row.filter_automated_emails,
            filter_non_business_emails=row.filter_non_business_emails,
            filter_custom_rules=row.filter_custom_rules,
            automation_enabled=row.automation_enabled,
            automation_interval_minutes=row.automation_interval_minutes,
            automation_max_emails_per_run=row.automation_max_emails_per_run,
            automation_last_run_at=(
                row.automation_last_run_at.isoformat() if row.automation_last_run_at else None
            ),
            automation_last_error=row.automation_last_error,
            one_reply_per_thread=row.one_reply_per_thread,
            sync_only_customer_unread=row.sync_only_customer_unread,
            verify_gmail_thread_before_reply=row.verify_gmail_thread_before_reply,
            use_thread_context=row.use_thread_context,
            default_model=settings.openai_model,
            **key_info,
        )

    def update_settings(
        self,
        db: Session,
        user: User,
        data: AIEmailAssistantSettingsUpdate,
        store_id: str | None = None,
    ) -> AIEmailAssistantSettingsResponse:
        store = self._ensure_store(db, user, store_id)
        if data.gmail_account_id:
            acc = db.get(GmailAccount, data.gmail_account_id)
            if not acc or acc.owner_id != user.id:
                raise HTTPException(status_code=400, detail="Invalid Gmail account")
            if not self._gmail_linked_to_store(
                db, gmail_account_id=acc.id, store_id=store.id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="That Gmail account is not linked to this store. Connect it under Settings → Gmail for this store.",
                )

        row = self.get_or_create_settings(db, user, store.id)
        row.business_name = data.business_name
        row.business_type = data.business_type
        row.tone_of_voice = data.tone_of_voice
        row.rules = data.rules
        row.policies = data.policies
        row.faq = data.faq
        row.auto_send_enabled = data.auto_send_enabled
        row.gmail_account_id = data.gmail_account_id
        row.openai_model = data.openai_model
        row.email_filter_enabled = data.email_filter_enabled
        row.filter_automated_emails = data.filter_automated_emails
        row.filter_non_business_emails = data.filter_non_business_emails
        row.filter_custom_rules = data.filter_custom_rules
        row.automation_enabled = data.automation_enabled
        row.automation_interval_minutes = data.automation_interval_minutes
        row.automation_max_emails_per_run = data.automation_max_emails_per_run
        row.one_reply_per_thread = data.one_reply_per_thread
        row.sync_only_customer_unread = data.sync_only_customer_unread
        row.verify_gmail_thread_before_reply = data.verify_gmail_thread_before_reply
        row.use_thread_context = data.use_thread_context
        db.commit()
        return self.get_settings_response(db, user, store.id)

    async def _fetch_customer_context(
        self,
        db: Session,
        settings_row: AIEmailAssistantSettings,
        account: GmailAccount,
        email: InboxEmail,
        *,
        force: bool = False,
    ) -> str | None:
        """Everything exchanged with this customer address, not just the current thread."""
        if not force and not settings_row.use_thread_context:
            return None

        client = GmailInboxClient(db)
        thread_messages = await client.get_thread_conversation(account, email.thread_id)

        earlier: list = []
        if email.sender_email:
            try:
                earlier = await client.get_customer_history(
                    account,
                    email.sender_email,
                    exclude_thread_id=email.thread_id,
                )
            except Exception:
                logger.warning(
                    "Could not load full history for %s", email.sender_email, exc_info=True
                )

        combined = format_customer_relationship(
            earlier,
            thread_messages,
            customer_email=email.sender_email or "",
        )
        return combined or None

    async def _duplicate_skip_reason(
        self,
        db: Session,
        settings_row: AIEmailAssistantSettings,
        account: GmailAccount,
        email: InboxEmail,
    ) -> str | None:
        """Hard skip only when Gmail shows we already sent the latest message.

        Whether a prior reply already resolved the customer's issue is decided by the AI
        after reading full thread history — not by blindly skipping the whole conversation.
        """
        if not settings_row.verify_gmail_thread_before_reply:
            return None

        client = GmailInboxClient(db)
        if await client.we_sent_last_in_thread(account, email.thread_id):
            return (
                "The latest message in this thread is already from your business — "
                "skipping to avoid sending duplicate replies."
            )
        return None

    async def _mark_email_read_in_gmail(
        self,
        db: Session,
        email: InboxEmail,
        account: GmailAccount | None = None,
        *,
        entire_thread: bool = True,
    ) -> None:
        """Remove UNREAD in Gmail so the bot (and the Gmail UI) will not see it again.

        Always clears the specific message, and by default the whole thread too —
        including filtered spam/newsletter mail the AI decided not to answer.
        """
        acct = account or db.get(GmailAccount, email.gmail_account_id)
        if not acct:
            return
        client = GmailInboxClient(db)
        msg_ok = await client.mark_as_read(acct, email.gmail_message_id)
        thread_ok = True
        if entire_thread and email.thread_id:
            thread_ok = await client.mark_thread_as_read(acct, email.thread_id)
        if not msg_ok and not thread_ok:
            logger.warning(
                "Failed to mark Gmail message %s as read (account=%s). "
                "Reconnect Gmail so the app has the gmail.modify scope.",
                email.gmail_message_id,
                acct.id,
            )

    async def _skip_email_as_duplicate(
        self,
        db: Session,
        email: InboxEmail,
        reason: str,
        *,
        account: GmailAccount | None = None,
        mark_read: bool = True,
    ) -> None:
        email.status = InboxEmailStatus.SKIPPED.value
        email.skip_reason = reason
        email.processed_at = datetime.now(UTC)
        db.commit()
        if mark_read:
            await self._mark_email_read_in_gmail(db, email, account)

    async def _skip_if_no_longer_unread_in_gmail(
        self,
        db: Session,
        account: GmailAccount,
        email: InboxEmail,
    ) -> bool:
        """Skip processing if the message is already read in Gmail."""
        client = GmailInboxClient(db)
        if await client.is_message_unread(account, email.gmail_message_id):
            return False
        email.status = InboxEmailStatus.PROCESSED.value
        email.skip_reason = "Already marked as read in Gmail — no reply needed."
        email.processed_at = datetime.now(UTC)
        db.commit()
        return True

    def _business_context(self, settings_row: AIEmailAssistantSettings) -> BusinessContext:
        return BusinessContext(
            business_name=settings_row.business_name,
            business_type=settings_row.business_type,
            tone_of_voice=settings_row.tone_of_voice,
            rules=settings_row.rules,
            policies=settings_row.policies,
            faq=settings_row.faq,
        )

    def _serialize_reply(self, reply: AIEmailReply, intent: str | None = None) -> AIReplyResponse:
        effective = reply.edited_body or reply.generated_body
        return AIReplyResponse(
            id=reply.id,
            inbox_email_id=reply.inbox_email_id,
            generated_body=reply.generated_body,
            edited_body=reply.edited_body,
            effective_body=effective,
            status=reply.status,
            model_used=reply.model_used,
            detected_intent=intent,
            error_message=reply.error_message,
            created_at=reply.created_at.isoformat(),
            sent_at=reply.sent_at.isoformat() if reply.sent_at else None,
        )

    def _serialize_inbox(self, email: InboxEmail) -> InboxEmailResponse:
        latest = None
        if email.replies:
            draft_or_sent = sorted(email.replies, key=lambda r: r.created_at, reverse=True)[0]
            latest = self._serialize_reply(draft_or_sent, email.detected_intent)
        return InboxEmailResponse(
            id=email.id,
            gmail_message_id=email.gmail_message_id,
            thread_id=email.thread_id,
            sender=email.sender,
            sender_email=email.sender_email,
            subject=email.subject,
            body_text=email.body_text,
            detected_intent=email.detected_intent,
            skip_reason=email.skip_reason,
            filter_category=email.filter_category,
            status=email.status,
            received_at=email.received_at.isoformat(),
            latest_reply=latest,
        )

    async def _apply_email_filter(
        self,
        db: Session,
        user: User,
        email: InboxEmail,
        settings_row: AIEmailAssistantSettings,
    ) -> None:
        """Decide reply vs ignore using full thread history; mark ignored mail as read."""
        api_key = resolve_openai_api_key(user)
        ai = AIService(model=settings_row.openai_model, api_key=api_key) if api_key else None

        thread_context: str | None = None
        account = db.get(GmailAccount, email.gmail_account_id)
        if account:
            thread_context = await self._fetch_customer_context(
                db, settings_row, account, email, force=True
            )

        config = config_from_settings(settings_row)

        # Even with the smart filter toggle off, use AI + full history to decide whether
        # the issue was already answered (reply vs leave as read).
        if not config.enabled:
            if not ai:
                return
            result = await ai.classify_should_reply(
                sender=email.sender,
                subject=email.subject,
                email_body=email.body_text,
                business_name=settings_row.business_name,
                business_type=settings_row.business_type,
                custom_skip_rules=settings_row.filter_custom_rules or "",
                thread_context=thread_context,
                model_override=settings_row.openai_model,
            )
        else:
            result = await evaluate_email_filter(
                config,
                sender=email.sender,
                sender_email=email.sender_email,
                subject=email.subject,
                body=email.body_text,
                thread_context=thread_context,
                ai=ai,
            )

        if not result.should_reply:
            email.status = InboxEmailStatus.SKIPPED.value
            email.skip_reason = result.reason or "Filtered — does not need a reply"
            email.filter_category = result.category
            email.processed_at = datetime.now(UTC)
            db.commit()
            # Spam / automated / already_resolved / etc. — always clear UNREAD in Gmail
            # so filtered mail does not sit unread in the mailbox.
            await self._mark_email_read_in_gmail(db, email, account)
            logger.info(
                "Filtered inbox %s (%s): %s — marked read in Gmail",
                email.id,
                result.category or "other",
                (result.reason or "")[:120],
            )

    def list_inbox(
        self, db: Session, user: User, *, store_id: str | None = None, limit: int = 50
    ) -> list[InboxEmailResponse]:
        store = self._ensure_store(db, user, store_id)
        emails = db.scalars(
            select(InboxEmail)
            .where(
                InboxEmail.user_id == user.id,
                InboxEmail.store_id == store.id,
            )
            .order_by(InboxEmail.received_at.desc())
            .limit(limit)
        ).all()
        return [self._serialize_inbox(e) for e in emails]

    def _assistant_note_for_email(self, email: InboxEmail) -> str:
        """Short monitoring note explaining what the assistant did / will do."""
        if email.status == InboxEmailStatus.SKIPPED.value:
            reason = email.skip_reason or "left unread as not needing a reply"
            return f"Assistant filtered this conversation — {reason}"
        if email.status == InboxEmailStatus.REPLIED.value:
            return "Assistant already replied in this thread via Gmail."
        if email.status == InboxEmailStatus.DRAFT_PENDING.value:
            return "Assistant drafted a reply — review it below before sending."
        if email.status == InboxEmailStatus.NEW.value:
            return "Waiting on the assistant — open Write AI reply or let autopilot handle it."
        return f"Assistant status: {email.status}"

    async def get_inbox_thread(
        self, db: Session, user: User, inbox_email_id: str
    ) -> InboxThreadResponse:
        """Load the Gmail conversation for mailbox-style monitoring."""
        email = db.get(InboxEmail, inbox_email_id)
        if not email or email.user_id != user.id:
            raise HTTPException(status_code=404, detail="Email not found")

        messages: list[ThreadMessageResponse] = []
        account = db.get(GmailAccount, email.gmail_account_id)
        if account and account.status == GmailAccountStatus.CONNECTED.value:
            client = GmailInboxClient(db)
            parts = await client.get_thread_conversation(
                account, email.thread_id, max_messages=40
            )
            messages = [
                ThreadMessageResponse(
                    message_id=p.message_id,
                    from_header=p.from_header,
                    body_text=p.body_text,
                    is_from_business=p.is_from_business,
                    sent_at=p.sent_at,
                    snippet=p.snippet or (p.body_text[:160] if p.body_text else ""),
                )
                for p in parts
            ]

        # Fallback when Gmail thread can't be loaded — still show the stored message
        if not messages and email.body_text:
            messages = [
                ThreadMessageResponse(
                    message_id=email.gmail_message_id,
                    from_header=email.sender or email.sender_email,
                    body_text=email.body_text,
                    is_from_business=False,
                    sent_at=email.received_at.isoformat() if email.received_at else None,
                    snippet=email.body_text[:160],
                )
            ]

        # Surface a pending AI draft as a provisional bubble for monitoring
        latest_reply = None
        if email.replies:
            latest_reply = sorted(email.replies, key=lambda r: r.created_at, reverse=True)[0]

        if latest_reply and latest_reply.status == AIReplyStatus.DRAFT.value:
            draft_body = latest_reply.edited_body or latest_reply.generated_body
            if draft_body:
                last = messages[-1] if messages else None
                already_shown = (
                    last
                    and last.is_from_business
                    and (last.body_text or "").strip() == draft_body.strip()
                )
                if not already_shown:
                    messages = [
                        *messages,
                        ThreadMessageResponse(
                            message_id=f"draft:{latest_reply.id}",
                            from_header="AI Assistant (draft)",
                            body_text=draft_body,
                            is_from_business=True,
                            sent_at=None,
                            snippet=draft_body[:160],
                        ),
                    ]

        return InboxThreadResponse(
            inbox_email=self._serialize_inbox(email),
            messages=messages,
            message_count=len(messages),
            assistant_note=self._assistant_note_for_email(email),
        )

    def _serialize_related_order(self, row: OrderTracking, *, match_reason: str) -> RelatedOrderItem:
        serialized = TrackingService._serialize_order(row)
        return RelatedOrderItem(
            id=serialized["id"],
            order_number=serialized["order_number"],
            customer_email=serialized["customer_email"],
            customer_name=serialized.get("customer_name"),
            tracking_number=serialized.get("tracking_number"),
            carrier=serialized.get("carrier"),
            status=serialized["status"],
            shopify_financial_status=serialized.get("shopify_financial_status"),
            shopify_fulfillment_status=serialized.get("shopify_fulfillment_status"),
            order_total=serialized.get("order_total"),
            currency=serialized.get("currency"),
            order_placed_at=serialized.get("order_placed_at"),
            match_reason=match_reason,
            last_updated_at=serialized.get("last_updated_at"),
        )

    async def get_related_orders(
        self, db: Session, user: User, inbox_email_id: str
    ) -> RelatedOrdersResponse:
        """Find Shopify orders for this conversation (by customer email + order #s in the mail)."""
        email = db.get(InboxEmail, inbox_email_id)
        if not email or email.user_id != user.id:
            raise HTTPException(status_code=404, detail="Email not found")

        customer_email = normalize_email(email.sender_email)
        if not email.store_id:
            return RelatedOrdersResponse(
                customer_email=customer_email,
                message="This email is not linked to a Shopify store.",
            )

        store = db.get(Store, email.store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")

        store_connected = store.status == StoreStatus.CONNECTED.value and bool(
            store.access_token_encrypted
        )
        if not store_connected:
            return RelatedOrdersResponse(
                customer_email=customer_email,
                shop_domain=store.shop_domain,
                store_connected=False,
                message="Connect this Shopify store to see matching customer orders.",
            )

        mentioned = extract_order_numbers(email.subject, email.body_text)
        by_id: dict[str, RelatedOrderItem] = {}

        # 1) All local orders for this customer email
        if customer_email:
            rows = db.scalars(
                select(OrderTracking)
                .where(
                    OrderTracking.store_id == store.id,
                    OrderTracking.customer_email == customer_email,
                )
                .order_by(OrderTracking.order_placed_at.desc().nullslast())
                .limit(12)
            ).all()
            for row in rows:
                by_id[row.id] = self._serialize_related_order(row, match_reason="customer_email")

        # 2) Local lookup for order numbers mentioned in the email
        for number in mentioned:
            variants = {
                normalize_order_number(v) for v in order_number_variants(number)
            }
            variants.discard("")
            if not variants:
                continue
            row = db.scalar(
                select(OrderTracking)
                .where(
                    OrderTracking.store_id == store.id,
                    OrderTracking.order_number_normalized.in_(variants),
                )
                .order_by(OrderTracking.order_placed_at.desc().nullslast())
                .limit(1)
            )
            if row and row.id not in by_id:
                reason = (
                    "customer_email"
                    if customer_email and row.customer_email == customer_email
                    else "order_number_in_email"
                )
                by_id[row.id] = self._serialize_related_order(row, match_reason=reason)

        # 3) Live Shopify lookup for mentioned numbers still missing (and matching email)
        missing_numbers = [
            n
            for n in mentioned
            if not any(
                normalize_order_number(item.order_number) == n
                or normalize_order_number(item.order_number.lstrip("#")) == n
                for item in by_id.values()
            )
        ]
        if missing_numbers and customer_email:
            tracker = TrackOrderService(db)
            for number in missing_numbers[:5]:
                try:
                    row = await tracker._fetch_from_shopify(store, number, customer_email)
                except Exception:
                    logger.exception("Shopify related-order lookup failed for %s", number)
                    continue
                if row and row.id not in by_id:
                    by_id[row.id] = self._serialize_related_order(
                        row, match_reason="order_number_in_email"
                    )

        orders = sorted(
            by_id.values(),
            key=lambda o: o.order_placed_at or o.last_updated_at or "",
            reverse=True,
        )[:12]

        message = None
        if not orders:
            message = (
                f"No Shopify orders found for {customer_email or 'this sender'}."
                if customer_email
                else "No customer email on this message to match orders."
            )

        return RelatedOrdersResponse(
            customer_email=customer_email,
            shop_domain=store.shop_domain,
            store_connected=True,
            orders=orders,
            message=message,
        )

    async def sync_inbox(
        self,
        db: Session,
        user: User,
        *,
        gmail_account_id: str,
        store_id: str | None = None,
        max_results: int = 15,
    ) -> list[InboxEmailResponse]:
        store = self._ensure_store(db, user, store_id)
        account = db.get(GmailAccount, gmail_account_id)
        if not account or account.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Gmail account not found")
        if account.status != GmailAccountStatus.CONNECTED.value:
            raise HTTPException(status_code=400, detail="Gmail account is not connected")
        if not self._gmail_linked_to_store(
            db, gmail_account_id=account.id, store_id=store.id
        ):
            raise HTTPException(
                status_code=400,
                detail="Gmail account is not linked to this store. Connect it under Settings → Gmail.",
            )

        settings_row = self.get_or_create_settings(db, user, store.id)
        client = GmailInboxClient(db)
        summaries = await client.list_unread_messages(
            account,
            max_results=max_results,
            only_customer_messages=settings_row.sync_only_customer_unread,
        )
        synced: list[InboxEmail] = []

        for item in summaries:
            msg_id = item["id"]
            exists = db.scalar(
                select(InboxEmail).where(
                    InboxEmail.gmail_account_id == account.id,
                    InboxEmail.gmail_message_id == msg_id,
                )
            )
            if exists:
                # Already handled (filtered / drafted / replied) — clear UNREAD so Gmail
                # and the next sync do not keep surfacing the same message.
                if exists.status != InboxEmailStatus.NEW.value:
                    thread_id = item.get("threadId") or exists.thread_id
                    if thread_id:
                        await client.mark_thread_as_read(account, thread_id)
                    else:
                        await client.mark_as_read(account, msg_id)
                continue

            detail = await client.get_message(account, msg_id)
            if not detail:
                continue

            # Do not hard-skip threads we already answered — a follow-up may raise a new issue.
            # AI classification (with full history) decides reply vs ignore + mark as read.
            if settings_row.verify_gmail_thread_before_reply:
                if await client.we_sent_last_in_thread(account, detail.thread_id):
                    # We already replied last — mark the whole thread read so leftover
                    # unread messages in that conversation do not stick in Gmail.
                    await client.mark_thread_as_read(account, detail.thread_id)
                    continue

            sender_email = client.parse_sender_email(detail.sender)
            row = InboxEmail(
                user_id=user.id,
                store_id=store.id,
                gmail_account_id=account.id,
                gmail_message_id=detail.message_id,
                thread_id=detail.thread_id,
                sender=detail.sender,
                sender_email=sender_email,
                subject=detail.subject,
                body_text=detail.body_text,
                status=InboxEmailStatus.NEW.value,
            )
            db.add(row)
            db.flush()
            synced.append(row)

        for row in synced:
            await self._apply_email_filter(db, user, row, settings_row)

        db.commit()
        for row in synced:
            db.refresh(row)
            # Safety: filtered/skipped mail must never stay unread in Gmail.
            if row.status == InboxEmailStatus.SKIPPED.value:
                await self._mark_email_read_in_gmail(db, row, account)

        await self.process_pending_replies(
            db, user, settings_row, store_id=store.id, limit=max_results
        )

        # After replies, clear UNREAD again for anything that ended as skipped/processed.
        for row in synced:
            db.refresh(row)
            if row.status in (
                InboxEmailStatus.SKIPPED.value,
                InboxEmailStatus.PROCESSED.value,
                InboxEmailStatus.REPLIED.value,
                InboxEmailStatus.DRAFT_PENDING.value,
            ):
                await self._mark_email_read_in_gmail(db, row, account)

        all_recent = self.list_inbox(db, user, store_id=store.id, limit=max_results)
        return all_recent

    async def start_full_history_scan(
        self,
        db: Session,
        user: User,
        *,
        gmail_account_id: str,
        store_id: str | None = None,
        max_threads: int = 100,
        confirmed: bool = False,
    ) -> FullHistoryScanResponse:
        """Validate and kick off a background full-history scan (returns immediately)."""
        from app.ai_email_assistant.full_scan_worker import start_full_history_scan as enqueue_scan

        if not confirmed:
            raise HTTPException(
                status_code=400,
                detail=(
                    "You must confirm that Check inbox will scan your full Gmail history "
                    "from the start of the mailbox."
                ),
            )

        account = db.get(GmailAccount, gmail_account_id)
        if not account or account.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Gmail account not found")
        if account.status != GmailAccountStatus.CONNECTED.value:
            raise HTTPException(status_code=400, detail="Gmail account is not connected")
        if not resolve_openai_api_key(user):
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key before running a full inbox check.",
            )

        store = self._ensure_store(db, user, store_id)
        if not self._gmail_linked_to_store(
            db, gmail_account_id=account.id, store_id=store.id
        ):
            raise HTTPException(
                status_code=400,
                detail="Gmail account is not linked to this store. Connect it under Settings → Gmail.",
            )

        settings_row = self.get_or_create_settings(db, user, store.id)
        from app.ai_email_assistant.full_scan_worker import is_scan_running

        if settings_row.full_scan_status == "running" and is_scan_running(settings_row.id):
            return self.get_full_scan_status(db, user, store_id=store.id)

        settings_row.full_scan_status = "running"
        settings_row.full_scan_message = "Starting full inbox check…"
        settings_row.full_scan_progress = 0
        settings_row.full_scan_total = max_threads
        settings_row.full_scan_started_at = datetime.now(UTC)
        settings_row.full_scan_finished_at = None
        db.commit()

        started = await enqueue_scan(
            settings_id=settings_row.id,
            user_id=user.id,
            gmail_account_id=gmail_account_id,
            store_id=store.id,
            max_threads=max_threads,
        )
        if not started:
            return self.get_full_scan_status(db, user, store_id=store.id)

        return FullHistoryScanResponse(
            status="running",
            message="Full inbox check started in the background. This can take several minutes.",
            progress=0,
            total=max_threads,
            started_at=settings_row.full_scan_started_at.isoformat(),
        )

    def get_full_scan_status(
        self, db: Session, user: User, *, store_id: str | None = None
    ) -> FullHistoryScanResponse:
        settings_row = self.get_or_create_settings(db, user, store_id)
        status = settings_row.full_scan_status or "idle"
        inbox: list = []
        if status in ("completed", "failed", "idle"):
            # Refresh inbox list when the job is done so the UI can update.
            if status == "completed":
                inbox = self.list_inbox(db, user, store_id=store_id, limit=50)
        return FullHistoryScanResponse(
            status=status,
            message=settings_row.full_scan_message or "",
            progress=settings_row.full_scan_progress or 0,
            total=settings_row.full_scan_total or 0,
            threads_scanned=settings_row.full_scan_progress or 0,
            started_at=(
                settings_row.full_scan_started_at.isoformat()
                if settings_row.full_scan_started_at
                else None
            ),
            finished_at=(
                settings_row.full_scan_finished_at.isoformat()
                if settings_row.full_scan_finished_at
                else None
            ),
            inbox=inbox,
        )

    async def full_history_scan(
        self,
        db: Session,
        user: User,
        *,
        gmail_account_id: str,
        store_id: str | None = None,
        max_threads: int = 100,
        confirmed: bool = False,
        progress_cb=None,
    ) -> FullHistoryScanResponse:
        """Scan the entire inbox history, analyze each conversation, answer unanswered clients."""
        if not confirmed:
            raise HTTPException(
                status_code=400,
                detail=(
                    "You must confirm that Check inbox will scan your full Gmail history "
                    "from the start of the mailbox."
                ),
            )

        account = db.get(GmailAccount, gmail_account_id)
        if not account or account.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Gmail account not found")
        if account.status != GmailAccountStatus.CONNECTED.value:
            raise HTTPException(status_code=400, detail="Gmail account is not connected")
        if not resolve_openai_api_key(user):
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key before running a full inbox check.",
            )

        store = self._ensure_store(db, user, store_id)
        if not self._gmail_linked_to_store(
            db, gmail_account_id=account.id, store_id=store.id
        ):
            raise HTTPException(
                status_code=400,
                detail="Gmail account is not linked to this store. Connect it under Settings → Gmail.",
            )

        settings_row = self.get_or_create_settings(db, user, store.id)
        client = GmailInboxClient(db)
        if progress_cb:
            progress_cb(0, max_threads, "Listing Gmail conversations…")
        threads = await client.list_all_inbox_threads(
            account,
            max_threads=max_threads,
            only_customer_messages=settings_row.sync_only_customer_unread,
        )
        total = len(threads)
        if progress_cb:
            progress_cb(0, total, f"Analyzing {total} conversations…")

        imported = 0
        needs_reply = 0
        never_answered = 0
        skipped_already = 0
        skipped_filtered = 0
        synced_ids: list[str] = []

        for idx, thread_ref in enumerate(threads, start=1):
            thread_id = thread_ref.get("id")
            if not thread_id:
                if progress_cb and (idx % 5 == 0 or idx == total):
                    progress_cb(idx, total, f"Analyzing conversations… ({idx}/{total})")
                continue

            analysis = await client.analyze_thread_history(account, thread_id)
            if progress_cb and (idx % 5 == 0 or idx == total):
                progress_cb(idx, total, f"Analyzing conversations… ({idx}/{total})")
            if not analysis:
                continue

            # Team already sent the last message — conversation is waiting on the customer
            if not analysis.latest_from_customer:
                skipped_already += 1
                continue

            # Customer was last to write — may need a reply (never answered OR open follow-up)
            exists = db.scalar(
                select(InboxEmail).where(
                    InboxEmail.gmail_account_id == account.id,
                    InboxEmail.gmail_message_id == analysis.latest_message_id,
                )
            )
            if exists:
                # Still re-evaluate if stuck as new; otherwise skip re-import
                if exists.status == InboxEmailStatus.NEW.value:
                    synced_ids.append(exists.id)
                    if analysis.never_answered_by_team:
                        never_answered += 1
                    needs_reply += 1
                elif exists.status in (
                    InboxEmailStatus.REPLIED.value,
                    InboxEmailStatus.SKIPPED.value,
                    InboxEmailStatus.PROCESSED.value,
                ):
                    skipped_already += 1
                continue

            row = InboxEmail(
                user_id=user.id,
                store_id=store.id,
                gmail_account_id=account.id,
                gmail_message_id=analysis.latest_message_id,
                thread_id=analysis.thread_id,
                sender=analysis.customer_sender,
                sender_email=analysis.customer_email,
                subject=analysis.subject,
                body_text=analysis.latest_body,
                status=InboxEmailStatus.NEW.value,
            )
            db.add(row)
            db.flush()
            imported += 1
            needs_reply += 1
            if analysis.never_answered_by_team:
                never_answered += 1
            synced_ids.append(row.id)

        db.commit()

        # Filter + AI: full thread history decides reply vs skip for each candidate
        filter_total = len(synced_ids)
        if progress_cb:
            progress_cb(
                total,
                total,
                f"Classifying {filter_total} conversations that may need a reply…",
            )
        for f_idx, inbox_id in enumerate(synced_ids, start=1):
            email = db.get(InboxEmail, inbox_id)
            if not email or email.status != InboxEmailStatus.NEW.value:
                continue
            await self._apply_email_filter(db, user, email, settings_row)
            db.refresh(email)
            if email.status == InboxEmailStatus.SKIPPED.value:
                skipped_filtered += 1
            if progress_cb and (f_idx % 3 == 0 or f_idx == filter_total):
                progress_cb(
                    total,
                    total,
                    f"Classifying replies… ({f_idx}/{filter_total})",
                )

        if progress_cb:
            progress_cb(total, total, "Drafting and sending replies…")
        processed = await self.process_pending_replies(
            db,
            user,
            settings_row,
            store_id=store.id,
            limit=min(len(synced_ids) or 1, max_threads),
        )

        inbox = self.list_inbox(db, user, store_id=store.id, limit=50)
        message = (
            f"Scanned {len(threads)} conversations. "
            f"{never_answered} never answered by your team. "
            f"{needs_reply} needed a reply (customer wrote last). "
            f"{skipped_already} already waiting on the customer. "
            f"{processed} replies drafted or sent."
        )
        return FullHistoryScanResponse(
            threads_scanned=len(threads),
            imported=imported,
            needs_reply=needs_reply,
            never_answered=never_answered,
            skipped_already_answered=skipped_already,
            skipped_filtered=skipped_filtered,
            processed_replies=processed,
            message=message,
            inbox=inbox,
            status="completed",
            progress=len(threads),
            total=len(threads),
        )

    async def process_pending_replies(
        self,
        db: Session,
        user: User,
        settings_row: AIEmailAssistantSettings,
        *,
        store_id: str | None = None,
        limit: int = 10,
    ) -> int:
        """Generate (and optionally send) replies for inbox emails still awaiting a response."""
        if not resolve_openai_api_key(user):
            return 0

        scoped_store_id = store_id or settings_row.store_id
        if not scoped_store_id:
            return 0

        q = (
            select(InboxEmail)
            .where(
                InboxEmail.user_id == user.id,
                InboxEmail.status == InboxEmailStatus.NEW.value,
                InboxEmail.store_id == scoped_store_id,
            )
            .order_by(InboxEmail.received_at.asc())
            .limit(limit)
        )

        pending = db.scalars(q).all()
        processed = 0
        replied_threads: set[str] = set()

        for email in pending:
            db.refresh(email)
            if email.status != InboxEmailStatus.NEW.value:
                continue

            if find_sent_reply(email) or find_active_draft(email):
                # Draft/reply already exists — mark read so Gmail does not keep it unread.
                await self._mark_email_read_in_gmail(db, email)
                continue

            email_account = db.get(GmailAccount, email.gmail_account_id)
            if email_account:
                if await self._skip_if_no_longer_unread_in_gmail(db, email_account, email):
                    continue

            # Same-run guard: after we reply once in this batch, skip other NEW messages
            # in that thread (AI already handled the conversation). Follow-ups that arrive
            # later are still synced and classified against full history.
            if settings_row.one_reply_per_thread and email.thread_id in replied_threads:
                await self._skip_email_as_duplicate(
                    db, email, ALREADY_REPLIED_REASON, account=email_account
                )
                continue

            # Cross-run / concurrent guard: another worker may have drafted/sent already.
            if settings_row.one_reply_per_thread and thread_has_answered_in_db(
                db,
                gmail_account_id=email.gmail_account_id,
                thread_id=email.thread_id,
                exclude_inbox_id=email.id,
            ):
                await self._skip_email_as_duplicate(
                    db, email, ALREADY_REPLIED_REASON, account=email_account
                )
                continue

            if email_account and settings_row.verify_gmail_thread_before_reply:
                dup = await self._duplicate_skip_reason(db, settings_row, email_account, email)
                if dup:
                    await self._skip_email_as_duplicate(
                        db, email, dup, account=email_account
                    )
                    continue

            try:
                await self.generate_and_maybe_send(
                    db, user, email.id, store_id=scoped_store_id
                )
                processed += 1
                if settings_row.one_reply_per_thread:
                    replied_threads.add(email.thread_id)
            except OpenAIServiceError as exc:
                if exc.stop_autopilot and settings_row.automation_enabled:
                    stop_autopilot(db, settings_row, exc.user_message)
                raise
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                logger.warning("Skipped inbox %s: %s", email.id, detail)
                if exc.status_code in (401, 402, 403, 429, 502, 503):
                    if settings_row.automation_enabled:
                        stop_autopilot(db, settings_row, detail)
                    raise OpenAIServiceError(
                        user_message=detail,
                        stop_autopilot=True,
                        status_code=exc.status_code,
                    ) from exc
            except Exception as exc:
                parsed = openai_error_from_exception(exc)
                if parsed.stop_autopilot:
                    if settings_row.automation_enabled:
                        stop_autopilot(db, settings_row, parsed.user_message)
                    raise parsed from exc
                logger.exception("Failed to process inbox %s: %s", email.id, exc)
        return processed

    async def run_automation_now(
        self, db: Session, user: User, store_id: str | None = None
    ) -> dict:
        """Manual trigger: sync unread + process replies immediately."""
        from app.ai_email_assistant.automation_worker import run_automation_for_settings

        settings_row = self.get_or_create_settings(db, user, store_id)
        if not resolve_openai_api_key(user):
            raise HTTPException(
                status_code=400,
                detail="Configure your OpenAI API key before running autopilot.",
            )

        if not settings_row.gmail_account_id:
            gid = self.resolve_gmail_account_id(db, user, settings_row)
            if gid:
                settings_row.gmail_account_id = gid
                db.commit()

        if not self.resolve_gmail_account_id(db, user, settings_row):
            raise HTTPException(status_code=400, detail="Connect Gmail before running autopilot.")

        return await run_automation_for_settings(settings_row.id, force=True)

    async def generate_and_maybe_send(
        self,
        db: Session,
        user: User,
        inbox_email_id: str,
        *,
        store_id: str | None = None,
    ) -> AIReplyResponse:
        email = db.get(InboxEmail, inbox_email_id)
        if not email or email.user_id != user.id:
            raise HTTPException(status_code=404, detail="Email not found")

        store = self._ensure_store(db, user, store_id or email.store_id)
        if email.store_id is None:
            email.store_id = store.id
            db.commit()
        elif email.store_id != store.id:
            raise HTTPException(status_code=404, detail="Email not found for this store")

        settings_row = self.get_or_create_settings(db, user, store.id)
        db.refresh(email)

        # Idempotent: never create a second reply for an email that already has one.
        existing_sent = find_sent_reply(email)
        if existing_sent:
            return self._serialize_reply(existing_sent, email.detected_intent)

        existing_draft = find_active_draft(email)
        if existing_draft:
            if existing_draft.status == AIReplyStatus.SENDING.value:
                return self._serialize_reply(existing_draft, email.detected_intent)
            if existing_draft.model_used == GENERATING_MODEL_MARKER and not (
                existing_draft.generated_body or ""
            ).strip():
                raise HTTPException(
                    status_code=409,
                    detail="A reply is already being generated for this email.",
                )
            if settings_row.auto_send_enabled:
                return await self.approve_and_send(db, user, existing_draft.id)
            return self._serialize_reply(existing_draft, email.detected_intent)

        if email.status == InboxEmailStatus.SKIPPED.value:
            raise HTTPException(
                status_code=400,
                detail=email.skip_reason or "This email was filtered and does not need a reply.",
            )
        if email.status == InboxEmailStatus.REPLIED.value:
            raise HTTPException(status_code=400, detail="This email was already replied to.")

        account = db.get(GmailAccount, email.gmail_account_id)
        if account:
            if await self._skip_if_no_longer_unread_in_gmail(db, account, email):
                raise HTTPException(
                    status_code=400,
                    detail=email.skip_reason or "This email is no longer unread in Gmail.",
                )
            dup = await self._duplicate_skip_reason(db, settings_row, account, email)
            if dup:
                await self._skip_email_as_duplicate(db, email, dup, account=account)
                raise HTTPException(status_code=400, detail=dup)

        if settings_row.one_reply_per_thread and thread_has_answered_in_db(
            db,
            gmail_account_id=email.gmail_account_id,
            thread_id=email.thread_id,
            exclude_inbox_id=email.id,
        ):
            await self._skip_email_as_duplicate(
                db, email, ALREADY_REPLIED_REASON, account=account
            )
            raise HTTPException(status_code=400, detail=ALREADY_REPLIED_REASON)

        await self._apply_email_filter(db, user, email, settings_row)
        db.refresh(email)
        if email.status == InboxEmailStatus.SKIPPED.value:
            raise HTTPException(
                status_code=400,
                detail=email.skip_reason or "This email was filtered and does not need a reply.",
            )

        # Claim the inbox row + insert a placeholder draft BEFORE the slow AI call so
        # concurrent autopilot/UI runs cannot generate a second reply.
        reply = AIEmailReply(
            inbox_email_id=email.id,
            user_id=user.id,
            generated_body="",
            status=AIReplyStatus.DRAFT.value,
            model_used=GENERATING_MODEL_MARKER,
        )
        email.status = InboxEmailStatus.DRAFT_PENDING.value
        db.add(reply)
        db.commit()
        db.refresh(reply)

        if settings_row.one_reply_per_thread:
            mark_thread_siblings_handled(
                db,
                gmail_account_id=email.gmail_account_id,
                thread_id=email.thread_id,
                keep_inbox_id=email.id,
            )

        thread_context = None
        if account:
            thread_context = await self._fetch_customer_context(
                db, settings_row, account, email, force=True
            )

        try:
            ai = self._ai_service(user, settings_row)
            result = await ai.generate_reply(
                sender=email.sender,
                subject=email.subject,
                email_body=email.body_text,
                context=self._business_context(settings_row),
                thread_context=thread_context,
                model_override=settings_row.openai_model,
            )
        except OpenAIServiceError as exc:
            reply.status = AIReplyStatus.FAILED.value
            reply.error_message = exc.user_message
            email.status = InboxEmailStatus.NEW.value
            db.commit()
            raise HTTPException(
                status_code=self._http_status_for_ai_error(exc),
                detail=exc.user_message,
            ) from exc
        except Exception:
            reply.status = AIReplyStatus.FAILED.value
            reply.error_message = "Reply generation failed"
            email.status = InboxEmailStatus.NEW.value
            db.commit()
            raise

        email.detected_intent = result.intent
        email.status = InboxEmailStatus.DRAFT_PENDING.value
        reply.generated_body = result.body
        reply.model_used = result.model
        reply.prompt_snapshot = result.prompt_snapshot
        reply.error_message = None
        db.commit()
        db.refresh(reply)

        if settings_row.auto_send_enabled:
            return await self.approve_and_send(db, user, reply.id)

        # Draft-only mode: still mark read in Gmail so the bot does not re-scan it
        # and so it no longer appears unread when you open Gmail.
        await self._mark_email_read_in_gmail(db, email, account)
        return self._serialize_reply(reply, email.detected_intent)

    async def send_manual_reply(
        self,
        db: Session,
        user: User,
        inbox_email_id: str,
        body: str,
        *,
        store_id: str | None = None,
    ) -> AIReplyResponse:
        """Send a human-written reply via Gmail without calling OpenAI."""
        text = (body or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Reply body cannot be empty")

        email = db.get(InboxEmail, inbox_email_id)
        if not email or email.user_id != user.id:
            raise HTTPException(status_code=404, detail="Email not found")

        store = self._ensure_store(db, user, store_id or email.store_id)
        if email.store_id is None:
            email.store_id = store.id
        elif email.store_id != store.id:
            raise HTTPException(status_code=404, detail="Email not found for this store")

        account = db.get(GmailAccount, email.gmail_account_id)
        if not account or account.status != GmailAccountStatus.CONNECTED.value:
            raise HTTPException(status_code=400, detail="Connect Gmail before sending a reply")

        existing_sent = find_sent_reply(email)
        if existing_sent:
            return self._serialize_reply(existing_sent, email.detected_intent)

        # Allow replying to filtered threads from the in-app mailbox
        if email.status == InboxEmailStatus.SKIPPED.value:
            email.skip_reason = None
            email.filter_category = None

        # Reuse an existing draft if present; otherwise create a manual reply record
        existing_draft = find_active_draft(email)
        if existing_draft and existing_draft.status == AIReplyStatus.SENDING.value:
            return self._serialize_reply(existing_draft, email.detected_intent)
        if existing_draft and existing_draft.status == AIReplyStatus.DRAFT.value:
            existing_draft.edited_body = text
            existing_draft.model_used = (
                existing_draft.model_used
                if existing_draft.model_used
                and existing_draft.model_used != GENERATING_MODEL_MARKER
                else "manual"
            )
            reply = existing_draft
        else:
            reply = AIEmailReply(
                inbox_email_id=email.id,
                user_id=user.id,
                generated_body="",
                edited_body=text,
                status=AIReplyStatus.DRAFT.value,
                model_used="manual",
            )
            db.add(reply)

        email.status = InboxEmailStatus.DRAFT_PENDING.value
        db.commit()
        db.refresh(reply)
        return await self.approve_and_send(db, user, reply.id)

    async def approve_and_send(self, db: Session, user: User, reply_id: str) -> AIReplyResponse:
        reply = db.get(AIEmailReply, reply_id)
        if not reply or reply.user_id != user.id:
            raise HTTPException(status_code=404, detail="Reply not found")

        # Already finished — idempotent success.
        if reply.status == AIReplyStatus.SENT.value:
            return self._serialize_reply(reply, reply.inbox_email.detected_intent)

        # Another request is already sending this draft.
        if reply.status == AIReplyStatus.SENDING.value:
            return self._serialize_reply(reply, reply.inbox_email.detected_intent)

        if reply.status != AIReplyStatus.DRAFT.value:
            raise HTTPException(
                status_code=400,
                detail=f"Reply cannot be sent (status: {reply.status})",
            )

        body = (reply.edited_body or reply.generated_body or "").strip()
        if not body:
            raise HTTPException(status_code=400, detail="Reply body is empty")

        email = reply.inbox_email
        account = db.get(GmailAccount, email.gmail_account_id)
        if not account:
            raise HTTPException(status_code=400, detail="Gmail account missing")

        # Atomically claim this draft so concurrent approve/auto-send cannot double-send.
        claim = db.execute(
            update(AIEmailReply)
            .where(
                AIEmailReply.id == reply_id,
                AIEmailReply.status == AIReplyStatus.DRAFT.value,
            )
            .values(status=AIReplyStatus.SENDING.value, error_message=None)
        )
        db.commit()
        if claim.rowcount == 0:
            db.refresh(reply)
            if reply.status == AIReplyStatus.SENT.value:
                return self._serialize_reply(reply, email.detected_intent)
            if reply.status == AIReplyStatus.SENDING.value:
                return self._serialize_reply(reply, email.detected_intent)
            raise HTTPException(
                status_code=409,
                detail="Reply was already handled by another send attempt.",
            )

        db.refresh(reply)

        # Thread-level guard: a sibling message may already have been answered.
        if thread_has_sent_reply(
            db,
            gmail_account_id=email.gmail_account_id,
            thread_id=email.thread_id,
            exclude_reply_id=reply.id,
        ):
            reply.status = AIReplyStatus.REJECTED.value
            reply.error_message = ALREADY_REPLIED_REASON
            email.status = InboxEmailStatus.SKIPPED.value
            email.skip_reason = ALREADY_REPLIED_REASON
            email.processed_at = datetime.now(UTC)
            db.commit()
            await self._mark_email_read_in_gmail(db, email, account)
            raise HTTPException(status_code=400, detail=ALREADY_REPLIED_REASON)

        settings_row = self.get_or_create_settings(db, user, email.store_id)
        client = GmailInboxClient(db)

        # Final Gmail check right before send (closes the race after AI generation).
        if settings_row.verify_gmail_thread_before_reply:
            if await client.we_sent_last_in_thread(account, email.thread_id):
                reply.status = AIReplyStatus.REJECTED.value
                reply.error_message = (
                    "The latest message in this thread is already from your business — "
                    "skipped to avoid sending a duplicate reply."
                )
                email.status = InboxEmailStatus.SKIPPED.value
                email.skip_reason = reply.error_message
                email.processed_at = datetime.now(UTC)
                db.commit()
                await client.mark_thread_as_read(account, email.thread_id)
                raise HTTPException(status_code=400, detail=reply.error_message)

        send_result = await client.send_thread_reply(
            account,
            to=email.sender_email,
            subject=email.subject,
            body_text=body,
            thread_id=email.thread_id,
            in_reply_to_message_id=email.gmail_message_id,
        )

        if not send_result:
            # Revert to draft so the user/autopilot can retry without creating a second reply.
            reply.status = AIReplyStatus.DRAFT.value
            reply.error_message = "Failed to send via Gmail API"
            email.status = InboxEmailStatus.DRAFT_PENDING.value
            db.commit()
            raise HTTPException(status_code=502, detail="Failed to send reply via Gmail")

        reply.status = AIReplyStatus.SENT.value
        reply.sent_at = datetime.now(UTC)
        reply.gmail_sent_message_id = send_result.get("id")
        reply.error_message = None
        email.status = InboxEmailStatus.REPLIED.value
        email.processed_at = datetime.now(UTC)
        db.commit()

        mark_thread_siblings_handled(
            db,
            gmail_account_id=email.gmail_account_id,
            thread_id=email.thread_id,
            keep_inbox_id=email.id,
        )
        await client.mark_thread_as_read(account, email.thread_id)

        return self._serialize_reply(reply, email.detected_intent)

    async def reject_reply(self, db: Session, user: User, reply_id: str) -> AIReplyResponse:
        reply = db.get(AIEmailReply, reply_id)
        if not reply or reply.user_id != user.id:
            raise HTTPException(status_code=404, detail="Reply not found")
        if reply.status == AIReplyStatus.SENT.value:
            raise HTTPException(status_code=400, detail="Cannot reject a reply that was already sent")
        if reply.status == AIReplyStatus.SENDING.value:
            raise HTTPException(status_code=400, detail="Reply is currently sending")
        reply.status = AIReplyStatus.REJECTED.value
        reply.inbox_email.status = InboxEmailStatus.PROCESSED.value
        db.commit()
        await self._mark_email_read_in_gmail(db, reply.inbox_email)
        return self._serialize_reply(reply, reply.inbox_email.detected_intent)

    def update_draft(self, db: Session, user: User, reply_id: str, body: str) -> AIReplyResponse:
        reply = db.get(AIEmailReply, reply_id)
        if not reply or reply.user_id != user.id:
            raise HTTPException(status_code=404, detail="Reply not found")
        if reply.status != AIReplyStatus.DRAFT.value:
            raise HTTPException(status_code=400, detail="Only draft replies can be edited")
        reply.edited_body = body
        db.commit()
        return self._serialize_reply(reply, reply.inbox_email.detected_intent)

    def unskip_email(self, db: Session, user: User, inbox_email_id: str) -> InboxEmailResponse:
        """Allow the user to reply to an email that was filtered."""
        email = db.get(InboxEmail, inbox_email_id)
        if not email or email.user_id != user.id:
            raise HTTPException(status_code=404, detail="Email not found")
        if email.status != InboxEmailStatus.SKIPPED.value:
            raise HTTPException(status_code=400, detail="Only filtered emails can be marked for reply")
        email.status = InboxEmailStatus.NEW.value
        email.skip_reason = None
        email.filter_category = None
        email.processed_at = None
        db.commit()
        db.refresh(email)
        return self._serialize_inbox(email)

    def list_reply_logs(
        self, db: Session, user: User, *, store_id: str | None = None, limit: int = 50
    ) -> list[AIReplyLogEntry]:
        store = self._ensure_store(db, user, store_id)
        replies = db.scalars(
            select(AIEmailReply)
            .join(InboxEmail, AIEmailReply.inbox_email_id == InboxEmail.id)
            .where(
                AIEmailReply.user_id == user.id,
                InboxEmail.store_id == store.id,
            )
            .order_by(AIEmailReply.created_at.desc())
            .limit(limit)
        ).all()
        entries: list[AIReplyLogEntry] = []
        for r in replies:
            inbox = r.inbox_email
            body = r.edited_body or r.generated_body
            entries.append(
                AIReplyLogEntry(
                    id=r.id,
                    inbox_email_id=r.inbox_email_id,
                    subject=inbox.subject,
                    sender_email=inbox.sender_email,
                    status=r.status,
                    model_used=r.model_used,
                    body_preview=body[:200],
                    created_at=r.created_at.isoformat(),
                    sent_at=r.sent_at.isoformat() if r.sent_at else None,
                )
            )
        return entries

    def get_stats(
        self, db: Session, user: User, *, store_id: str | None = None
    ) -> AIEmailAssistantStatsResponse:
        """Aggregate inbox + reply metrics for the store-owner Stats dashboard."""
        store = self._ensure_store(db, user, store_id)
        minutes_per_reply = 5

        def _inbox_base():
            return select(InboxEmail).where(
                InboxEmail.user_id == user.id,
                InboxEmail.store_id == store.id,
            )

        def _reply_base():
            return (
                select(AIEmailReply)
                .join(InboxEmail, AIEmailReply.inbox_email_id == InboxEmail.id)
                .where(
                    AIEmailReply.user_id == user.id,
                    InboxEmail.store_id == store.id,
                )
            )

        def _period_stats(since: datetime | None = None) -> PeriodStats:
            inbox_q = _inbox_base()
            reply_q = _reply_base()
            if since is not None:
                inbox_q = inbox_q.where(InboxEmail.received_at >= since)
                reply_q = reply_q.where(AIEmailReply.created_at >= since)

            emails = db.scalars(inbox_q).all()
            replies = db.scalars(reply_q).all()

            emails_received = len(emails)
            awaiting = sum(1 for e in emails if e.status == InboxEmailStatus.NEW.value)
            filtered = sum(1 for e in emails if e.status == InboxEmailStatus.SKIPPED.value)
            drafts = sum(1 for r in replies if r.status == AIReplyStatus.DRAFT.value)
            sent = sum(1 for r in replies if r.status == AIReplyStatus.SENT.value)
            # Also count inbox-level replied if reply rows lag
            replied_inbox = sum(1 for e in emails if e.status == InboxEmailStatus.REPLIED.value)
            sent = max(sent, replied_inbox)
            failed = sum(1 for r in replies if r.status == AIReplyStatus.FAILED.value)

            return PeriodStats(
                emails_received=emails_received,
                replies_sent=sent,
                drafts_pending=drafts,
                filtered=filtered,
                failed=failed,
                awaiting_reply=awaiting,
            )

        now = datetime.now(UTC)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        all_time = _period_stats(None)
        today = _period_stats(start_today)
        last_7 = _period_stats(week_ago)
        last_30 = _period_stats(month_ago)

        # Filter category breakdown (all time)
        filter_q = (
            select(InboxEmail.filter_category, func.count())
            .where(
                InboxEmail.user_id == user.id,
                InboxEmail.store_id == store.id,
                InboxEmail.status == InboxEmailStatus.SKIPPED.value,
            )
            .group_by(InboxEmail.filter_category)
        )
        filter_rows = db.execute(filter_q).all()
        filter_breakdown = [
            NamedCount(name=(name or "other"), count=int(count))
            for name, count in filter_rows
            if count
        ]
        filter_breakdown.sort(key=lambda x: x.count, reverse=True)

        intent_q = (
            select(InboxEmail.detected_intent, func.count())
            .where(
                InboxEmail.user_id == user.id,
                InboxEmail.store_id == store.id,
                InboxEmail.detected_intent.isnot(None),
            )
            .group_by(InboxEmail.detected_intent)
        )
        intent_rows = db.execute(intent_q).all()
        intent_breakdown = [
            NamedCount(name=str(name).replace("_", " "), count=int(count))
            for name, count in intent_rows
            if name and count
        ]
        intent_breakdown.sort(key=lambda x: x.count, reverse=True)

        unique_q = select(func.count(func.distinct(InboxEmail.sender_email))).where(
            InboxEmail.user_id == user.id,
            InboxEmail.store_id == store.id,
            InboxEmail.status == InboxEmailStatus.REPLIED.value,
        )
        unique_customers = db.scalar(unique_q) or 0

        minutes_saved = all_time.replies_sent * minutes_per_reply
        hours_saved = round(minutes_saved / 60, 1)

        filter_efficiency = (
            round((all_time.filtered / all_time.emails_received) * 100, 1)
            if all_time.emails_received
            else 0.0
        )
        reply_rate = (
            round((all_time.replies_sent / all_time.emails_received) * 100, 1)
            if all_time.emails_received
            else 0.0
        )

        settings_row = self.get_or_create_settings(db, user, store.id)
        gmail_id = self.resolve_gmail_account_id(db, user, settings_row)
        gmail_connected = gmail_id is not None

        return AIEmailAssistantStatsResponse(
            all_time=all_time,
            today=today,
            last_7_days=last_7,
            last_30_days=last_30,
            filter_breakdown=filter_breakdown,
            intent_breakdown=intent_breakdown,
            unique_customers_helped=int(unique_customers),
            minutes_saved_estimate=minutes_saved,
            hours_saved_estimate=hours_saved,
            filter_efficiency_pct=filter_efficiency,
            reply_rate_pct=reply_rate,
            autopilot_enabled=settings_row.automation_enabled,
            auto_send_enabled=settings_row.auto_send_enabled,
            automation_last_run_at=(
                settings_row.automation_last_run_at.isoformat()
                if settings_row.automation_last_run_at
                else None
            ),
            openai_configured=is_openai_configured(user),
            gmail_connected=gmail_connected,
        )
