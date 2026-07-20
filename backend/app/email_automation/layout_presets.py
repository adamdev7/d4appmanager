"""Pre-made email layout wrappers (theme color + optional logo slot)."""

from __future__ import annotations

LAYOUT_CLASSIC = "classic"
LAYOUT_MODERN = "modern"
LAYOUT_BOLD = "bold"

LAYOUT_PRESETS: list[dict[str, str]] = [
    {
        "id": LAYOUT_CLASSIC,
        "name": "Classic",
        "description": "Clean header bar, centered logo, simple body",
    },
    {
        "id": LAYOUT_MODERN,
        "name": "Modern",
        "description": "Accent stripe, left-aligned logo, spacious layout",
    },
    {
        "id": LAYOUT_BOLD,
        "name": "Bold",
        "description": "Full-color header with strong brand presence",
    },
]

DEFAULT_LAYOUT = LAYOUT_CLASSIC
DEFAULT_THEME_COLOR = "#0d9488"


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _logo_block(logo_url: str | None, *, max_height: int = 48, align: str = "center") -> str:
    if not logo_url:
        return ""
    src = _escape_attr(logo_url)
    return (
        f'<div style="text-align:{align};margin:0 0 20px;">'
        f'<img src="{src}" alt="Logo" '
        f'style="max-height:{max_height}px;max-width:220px;height:auto;display:inline-block;" />'
        f"</div>"
    )


def _normalize_body(body_html: str) -> str:
    text = (body_html or "").strip()
    if not text:
        return "<p style=\"margin:0;color:#374151;line-height:1.6;\">&nbsp;</p>"
    # Plain text pasted without tags → wrap paragraphs
    if "<" not in text:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not parts:
            parts = [text]
        return "".join(
            f'<p style="margin:0 0 12px;color:#374151;font-size:15px;line-height:1.6;">{_escape_attr(p).replace(chr(10), "<br/>")}</p>'
            for p in parts
        )
    return text


def render_layout(
    *,
    layout_preset: str,
    body_html: str,
    theme_color: str,
    logo_url: str | None,
    store_name: str,
) -> str:
    """Wrap inner message HTML in a branded layout. Omits logo block when no logo."""
    color = theme_color.strip() if theme_color and theme_color.strip() else DEFAULT_THEME_COLOR
    if not color.startswith("#"):
        color = f"#{color}"
    color = _escape_attr(color[:32])
    name = _escape_attr(store_name or "Your Store")
    inner = _normalize_body(body_html)
    preset = (layout_preset or DEFAULT_LAYOUT).lower()

    if preset == LAYOUT_MODERN:
        logo = _logo_block(logo_url, max_height=44, align="left")
        return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f3f4f6;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;">
<tr><td style="height:4px;background:{color};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:32px 36px 12px;">{logo}
<p style="margin:0 0 4px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#9ca3af;font-family:Arial,Helvetica,sans-serif;">{name}</p>
</td></tr>
<tr><td style="padding:8px 36px 36px;font-family:Arial,Helvetica,sans-serif;">{inner}</td></tr>
<tr><td style="padding:16px 36px 28px;border-top:1px solid #e5e7eb;">
<p style="margin:0;font-size:12px;color:#9ca3af;font-family:Arial,Helvetica,sans-serif;">Sent by {name}</p>
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    if preset == LAYOUT_BOLD:
        logo = _logo_block(logo_url, max_height=52, align="center")
        header_inner = logo or f'<p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;font-family:Arial,Helvetica,sans-serif;">{name}</p>'
        return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#111827;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="background:{color};padding:36px 28px;text-align:center;">{header_inner}</td></tr>
<tr><td style="padding:32px 28px;">{inner}</td></tr>
<tr><td style="padding:18px 28px 28px;background:#f9fafb;">
<p style="margin:0;font-size:12px;color:#6b7280;text-align:center;">© {name}</p>
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    # classic (default)
    logo = _logo_block(logo_url, max_height=48, align="center")
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
<tr><td style="background:{color};padding:18px 24px;text-align:center;">
<p style="margin:0;font-size:16px;font-weight:600;color:#ffffff;">{name}</p>
</td></tr>
<tr><td style="padding:28px 28px 8px;">{logo}</td></tr>
<tr><td style="padding:0 28px 28px;">{inner}</td></tr>
<tr><td style="padding:14px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;">
<p style="margin:0;font-size:12px;color:#64748b;text-align:center;">{name}</p>
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def absolute_logo_url(logo_path: str | None, app_url: str) -> str | None:
    """Turn a stored relative path into an absolute URL for email clients."""
    if not logo_path:
        return None
    path = logo_path.strip()
    if path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
        return path
    base = app_url.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"
