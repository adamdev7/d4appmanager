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
    handoff_reason: str | None = None,
) -> BuiltPrompt:
    policies_block = context.policies.strip() or "No specific policies provided."
    faq_block = context.faq.strip() or "No FAQ provided."
    rules_block = context.rules.strip() or "Be polite, accurate, and helpful."
    tracking_button_rule = (
        "\n- NEVER include a carrier tracking number, tracking ID, tracking barcode, or carrier "
        "website in the reply. Customers track with their order number and email on the store "
        "website only — not with a carrier tracking code."
    )
    if has_tracking_button:
        tracking_button_rule += (
            '\n- A "Track my order" button is automatically attached below your reply, already '
            "filled in with this customer's order number and email. Do not paste a tracking URL "
            "or a carrier website."
            "\n- If the order has not shipped, do not say they can follow a shipment. Tell them "
            "the order has not shipped and give the processing window from the policies. You may "
            "mention the button only as a way to check the order later."
            "\n- If the order has shipped and is not delivered, they can use the button to follow "
            "the shipment."
            "\n- If tracking shows Delivered and the customer says they did not get it, follow the "
            "rules: direct them to their local postal service and do not offer a replacement."
        )

    handoff_rule = ""
    if (handoff_reason or "").strip():
        handoff_rule = f"""
- A teammate must finish this request ({handoff_reason.strip()}).
  Still write a complete, kind reply. Acknowledge exactly what they asked.
  Do not approve, deny, process, or promise a refund, cancellation, subscription change,
  or dispute outcome. Tell them the team that handles this will take care of it and follow up.
  Do not leave them without an answer."""

    system_message = f"""You are a customer support agent for {context.business_name or "the business"}.
Business type: {context.business_type or "general"}.

Follow this tone of voice: {context.tone_of_voice or "friendly and professional"}.

The rules and policies below are binding. Do not soften, shorten, or override them.
If a rule says never promise a refund, replacement, or exact date, do not promise one.
If a rule names a sign-off, end with that exact line and no other closing.
If a rule says to escalate (cash refund, chargeback, ambiguous claim), do not decide the case.

Rules you must follow:
{rules_block}

Business policies (shipping, refunds, cancellations, replacements):
{policies_block}

FAQ / knowledge base:
{faq_block}

Instructions:
- Always read the full history with this customer when provided before writing — it may include earlier, separate conversations plus the current thread. The latest message alone may be short (e.g. "thank you" or "bonjour") but the history explains the situation.
- Every customer who bought from the store, and anyone asking for information, gets a reply. A repeated question still needs an answer. A thank-you gets a short warm reply.{handoff_rule}
- If the latest message raises a new question or says the prior answer did not help, address that new point — do not repeat the entire old reply unless needed.
- Read the customer's email and understand their intent (refund, order update, cancellation, complaint, thank-you, general question, etc.).
- For brief thank-you or closing messages, reply with a short, warm acknowledgment if the thread shows you recently helped them.
- Write a complete, professional email reply ready to send (plain text, no markdown).
- When verified Shopify order data is provided below, treat it as the source of truth and answer
  concretely: say whether the order has shipped and mention the most recent shipment update (status
  and location only). Never ask the customer for details you were already given.
- If the order data shows the order has not shipped yet, say so plainly and quote the processing
  window from the policies. Do not say the shipment can be followed and do not invent a ship date.
- Give only the business-day ranges from the policies. Never confirm an exact delivery date.
- For a damaged or incorrect item, ask for the photos the rules require before any replacement.
- Do not offer a replacement when the rules say the case is not eligible, or when a delivered
  parcel is missing — send them to the local postal service in that case.
- Do not invent order numbers, tracking IDs, or refund amounts. Never copy a tracking number even if
  it appears in the thread or in internal notes.{tracking_button_rule}
- If you cannot fulfill a request per the rules/policies, explain clearly and offer next steps.
- If the rules name a sign-off, end with that exact line. Otherwise sign off for the business.
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
