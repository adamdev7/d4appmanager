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
    order_context: str | None = None,
    has_tracking_button: bool = False,
) -> BuiltPrompt:
    policies_block = context.policies.strip() or "No specific policies provided."
    faq_block = context.faq.strip() or "No FAQ provided."
    rules_block = context.rules.strip() or "Be polite, accurate, and helpful."
    tracking_button_rule = ""
    if has_tracking_button:
        tracking_button_rule = (
            '\n- A "Track my order" button is automatically attached below your reply, already '
            "filled in with this customer's order number and email. Invite them to use it "
            "(e.g. \"you can follow your shipment with the button below\") and do not paste a "
            "tracking URL, a carrier website, or tracking instructions of your own."
        )

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
- Always read the full history with this customer when provided before writing — it may include earlier, separate conversations plus the current thread. The latest message alone may be short (e.g. "thank you") but the history explains the situation.
- Check whether the business already answered this customer's issue earlier in the thread. If the latest message only confirms or thanks you and needs no further help, keep the reply to a brief warm closing (or the filter may skip sending entirely).
- If the latest message raises a new question or says the prior answer did not help, address that new point — do not repeat the entire old reply unless needed.
- Read the customer's email and understand their intent (refund, order update, cancellation, complaint, thank-you, general question, etc.).
- For brief thank-you or closing messages, reply with a short, warm acknowledgment if the thread shows you recently helped them.
- Write a complete, professional email reply ready to send (plain text, no markdown).
- When verified Shopify order data is provided below, treat it as the source of truth and answer
  concretely: say whether the order has shipped, quote the tracking number and carrier, and mention
  the most recent shipment update. Never ask the customer for details you were already given.
- If the order data shows the order has not shipped yet, say so plainly and set expectations from the
  business shipping policy instead of implying a tracking number exists.
- Do not invent order numbers, tracking IDs, or refund amounts unless they appear in the thread or in
  the verified order data.{tracking_button_rule}
- If you cannot fulfill a request per the rules/policies, explain clearly and offer next steps.
- Sign off appropriately for the business.
- Output ONLY the email body text (no subject line, no "Subject:" prefix)."""

    thread_block = ""
    if thread_context and thread_context.strip():
        thread_block = f"""
Full email history with this customer:
{thread_context.strip()}

"""

    order_block = ""
    if order_context and order_context.strip():
        order_block = f"""{order_context.strip()}

"""

    user_message = f"""{order_block}{thread_block}Latest incoming customer email (reply to this):

From: {sender}
Subject: {subject}

{email_body.strip()}"""

    return BuiltPrompt(system_message=system_message, user_message=user_message)
