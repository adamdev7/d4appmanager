from dataclasses import dataclass


@dataclass
class BusinessContext:
    business_name: str
    business_type: str
    tone_of_voice: str
    rules: str
    policies: str
    faq: str


@dataclass
class BuiltPrompt:
    system_message: str
    user_message: str


def build_reply_prompt(
    *,
    context: BusinessContext,
    sender: str,
    subject: str,
    email_body: str,
    thread_context: str | None = None,
) -> BuiltPrompt:
    policies_block = context.policies.strip() or "No specific policies provided."
    faq_block = context.faq.strip() or "No FAQ provided."
    rules_block = context.rules.strip() or "Be polite, accurate, and helpful."

    system_message = f"""You are a customer support agent for {context.business_name or "the business"}.
Business type: {context.business_type or "general"}.

Follow this tone of voice: {context.tone_of_voice or "friendly and professional"}.

Rules you must follow:
{rules_block}

Business policies (shipping, refunds, cancellations, subscriptions, etc.):
{policies_block}

FAQ / knowledge base:
{faq_block}

Instructions:
- Always read the full conversation thread when provided before writing — the latest message alone may be short (e.g. "thank you") but the history explains the situation.
- Check whether the business already answered this customer's issue earlier in the thread. If the latest message only confirms or thanks you and needs no further help, keep the reply to a brief warm closing (or the filter may skip sending entirely).
- If the latest message raises a new question or says the prior answer did not help, address that new point — do not repeat the entire old reply unless needed.
- Read the customer's email and understand their intent (refund, order update, cancellation, complaint, thank-you, general question, etc.).
- For brief thank-you or closing messages, reply with a short, warm acknowledgment if the thread shows you recently helped them.
- Write a complete, professional email reply ready to send (plain text, no markdown).
- Do not invent order numbers, tracking IDs, or refund amounts unless they appear in the thread.
- If you cannot fulfill a request per the rules/policies, explain clearly and offer next steps.
- Sign off appropriately for the business.
- Output ONLY the email body text (no subject line, no "Subject:" prefix)."""

    thread_block = ""
    if thread_context and thread_context.strip():
        thread_block = f"""
Conversation thread (oldest to newest):
{thread_context.strip()}

"""

    user_message = f"""{thread_block}Latest incoming customer email (reply to this):

From: {sender}
Subject: {subject}

{email_body.strip()}"""

    return BuiltPrompt(system_message=system_message, user_message=user_message)
