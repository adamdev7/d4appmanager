"""Format Gmail thread history for AI classification and replies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThreadMessagePart:
    message_id: str
    from_header: str
    body_text: str
    is_from_business: bool


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
