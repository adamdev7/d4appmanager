"""Render an assistant reply as HTML so it can carry a "Track my order" button.

Replies stay plain text unless there is something to add — a text/plain alternative is
always sent alongside the HTML so clients that block rich mail still get the link.
"""

from __future__ import annotations

from html import escape

from app.ai_email_assistant.order_context import TrackingLink
from app.email_automation.layout_presets import DEFAULT_THEME_COLOR

TRACK_BUTTON_LABEL = "Track my order"


def _body_to_html(body_text: str) -> str:
    paragraphs = [block.strip() for block in (body_text or "").split("\n\n")]
    rendered = [
        f'<p style="margin:0 0 16px;">{escape(block).replace(chr(10), "<br>")}</p>'
        for block in paragraphs
        if block
    ]
    return "\n".join(rendered)


def _button_html(link: TrackingLink, theme_color: str) -> str:
    color = (theme_color or "").strip() or DEFAULT_THEME_COLOR
    details = [f"Order {escape(link.order_number)}"]
    if link.tracking_number:
        carrier = f" &middot; {escape(link.carrier)}" if link.carrier else ""
        details.append(f"Tracking {escape(link.tracking_number)}{carrier}")

    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:24px 0 8px;">
  <tr>
    <td align="center" bgcolor="{color}" style="border-radius:8px;">
      <a href="{escape(link.url, quote=True)}" target="_blank" rel="noopener"
         style="display:inline-block;padding:14px 32px;font-family:Helvetica,Arial,sans-serif;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;letter-spacing:0.02em;">
        {TRACK_BUTTON_LABEL} &rarr;
      </a>
    </td>
  </tr>
  <tr>
    <td style="padding-top:10px;font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#6b7280;">
      {" &middot; ".join(details)}
    </td>
  </tr>
</table>"""


def render_reply_html(
    body_text: str,
    *,
    tracking_link: TrackingLink | None,
    theme_color: str | None = None,
) -> str | None:
    """HTML alternative for the reply, or None when plain text is enough."""
    if not tracking_link:
        return None

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#ffffff;">
  <div style="font-family:Helvetica,Arial,sans-serif;font-size:15px;line-height:1.6;color:#111827;max-width:600px;">
    {_body_to_html(body_text)}
    {_button_html(tracking_link, theme_color or DEFAULT_THEME_COLOR)}
  </div>
</body>
</html>"""


def render_reply_text(body_text: str, *, tracking_link: TrackingLink | None) -> str:
    """Plain-text body, with the tracking link spelled out when a button was added."""
    text = (body_text or "").strip()
    if not tracking_link:
        return text

    lines = [text, "", f"{TRACK_BUTTON_LABEL}: {tracking_link.url}"]
    if tracking_link.tracking_number:
        carrier = f" ({tracking_link.carrier})" if tracking_link.carrier else ""
        lines.append(f"Tracking number: {tracking_link.tracking_number}{carrier}")
    return "\n".join(lines)
