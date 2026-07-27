"""Format Gmail thread history for AI classification and replies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThreadMessagePart:
    message_id: str
    from_header: str
    body_text: str
    is_from_business: bool
    sent_at: str | None = None
    snippet: str = ""


def format_thread_conversation(
    messages: list[ThreadMessagePart],
    *,
    max_chars: int = 12000,
) -> str:
    if not messages:
        return ""

    parts: list[str] = []
    total = 0
    for msg in messages:
        role = "Your business" if msg.is_from_business else "Customer"
        block = (
            f"--- {role} ({msg.from_header}) ---\n"
            f"{msg.body_text.strip()[:2500]}\n"
        )
        if total + len(block) > max_chars:
            parts.append("... (older messages omitted)\n")
            break
        parts.append(block)
        total += len(block)

    return "\n".join(parts).strip()


def format_customer_relationship(
    earlier_messages: list[ThreadMessagePart],
    thread_messages: list[ThreadMessagePart],
    *,
    customer_email: str = "",
) -> str:
    """Full history with one customer: earlier conversations, then the current thread."""
    sections: list[str] = []

    if earlier_messages:
        earlier = format_thread_conversation(earlier_messages, max_chars=6000)
        if earlier:
            who = f" with {customer_email}" if customer_email else ""
            sections.append(
                f"EARLIER EMAILS{who} (separate conversations, oldest to newest):\n{earlier}"
            )

    if thread_messages:
        current = format_thread_conversation(thread_messages, max_chars=10000)
        if current:
            sections.append(f"CURRENT CONVERSATION (oldest to newest):\n{current}")

    return "\n\n".join(sections).strip()
