"""Pre-made email layout wrappers (theme color + optional logo slot)."""

from __future__ import annotations

LAYOUT_CLASSIC = "classic"
LAYOUT_MODERN = "modern"
LAYOUT_BOLD = "bold"

LAYOUT_PRESETS: list[dict[str, str]] = [
    {
        "id": LAYOUT_CLASSIC,
        "name": "Classic",
        "description": "Centered store name, logo in the footer",
    },
    {
        "id": LAYOUT_MODERN,
        "name": "Modern",
        "description": "Accent stripe, centered name, logo in the footer",
    },
    {
        "id": LAYOUT_BOLD,
        "name": "Bold",
        "description": "Full-color header, centered name, logo in the footer",
    },
]

DEFAULT_LAYOUT = LAYOUT_CLASSIC
DEFAULT_THEME_COLOR = "#0d9488"

_BODY_TEXT = "#1f2937"
_FOOTER_TEXT = "#64748b"

# Soft caps only — keeps aspect ratio of the uploaded file (width/height auto).
_LOGO_MAX_WIDTH = 200
_LOGO_MAX_HEIGHT = 96


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _logo_block(
    logo_url: str | None,
    *,
    store_name: str = "",
    fallback_color: str = _BODY_TEXT,
    max_width: int = _LOGO_MAX_WIDTH,
    max_height: int = _LOGO_MAX_HEIGHT,
) -> str:
    """Centered footer logo at natural aspect ratio (soft-capped for email clients)."""
    if not logo_url:
        return ""
    src = _escape_attr(logo_url)
    fallback = _escape_attr(store_name or "Logo")
    color = _escape_attr(fallback_color)
    return (
        f'<div style="text-align:center;margin:0 0 14px;">'
        f'<img src="{src}" alt="{fallback}" '
        f'style="width:auto;height:auto;max-width:{max_width}px;max-height:{max_height}px;'
        f'display:inline-block;border:0;outline:none;" '
        f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\';" />'
        f'<p style="display:none;margin:0;font-size:16px;font-weight:600;color:{color};'
        f'font-family:Arial,Helvetica,sans-serif;">{fallback}</p>'
        f"</div>"
    )


def _normalize_body(body_html: str) -> str:
    text = (body_html or "").strip()
    if not text:
        return f'<p style="margin:0;color:{_BODY_TEXT};line-height:1.65;">&nbsp;</p>'
    # Plain text pasted without tags → wrap paragraphs
    if "<" not in text:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not parts:
            parts = [text]
        return "".join(
            f'<p style="margin:0 0 12px;color:{_BODY_TEXT};font-size:15px;line-height:1.65;">'
            f'{_escape_attr(p).replace(chr(10), "<br/>")}</p>'
            for p in parts
        )
    # Wrapper forces readable text color (avoids dark-mode UI inheritance in previews).
    return (
        f'<div style="color:{_BODY_TEXT};font-size:15px;line-height:1.65;'
        f'font-family:Arial,Helvetica,sans-serif;">{text}</div>'
    )


def _footer_block(store_name: str, reason: str, logo_html: str = "") -> str:
    name = store_name
    return (
        f"{logo_html}"
        f'<p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:{_FOOTER_TEXT};'
        f'text-align:center;font-family:Arial,Helvetica,sans-serif;">{name}</p>'
        f'<p style="margin:0;font-size:11px;line-height:1.5;color:{_FOOTER_TEXT};'
        f'text-align:center;font-family:Arial,Helvetica,sans-serif;">{reason}</p>'
    )


def render_layout(
    *,
    layout_preset: str,
    body_html: str,
    theme_color: str,
    logo_url: str | None,
    store_name: str,
) -> str:
    """Wrap inner message HTML in a branded layout. Logo sits in the footer when set."""
    color = theme_color.strip() if theme_color and theme_color.strip() else DEFAULT_THEME_COLOR
    if not color.startswith("#"):
        color = f"#{color}"
    color = _escape_attr(color[:32])
    name = _escape_attr(store_name or "Your Store")
    inner = _normalize_body(body_html)
    preset = (layout_preset or DEFAULT_LAYOUT).lower()
    reason = (
        f"This is a transactional message from {name}. "
        "If you have questions, reply to this email."
    )
    logo = _logo_block(logo_url, store_name=name)

    if preset == LAYOUT_MODERN:
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head>
<body style="margin:0;padding:0;background:#f3f4f6;color:{_BODY_TEXT};font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;">
<tr><td style="height:4px;background:{color};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:28px 36px 12px;text-align:center;">
<p style="margin:0 0 4px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-family:Arial,Helvetica,sans-serif;">{name}</p>
</td></tr>
<tr><td style="padding:8px 36px 36px;font-family:Arial,Helvetica,sans-serif;color:{_BODY_TEXT};">{inner}</td></tr>
<tr><td style="padding:20px 36px 28px;border-top:1px solid #e5e7eb;text-align:center;">
{_footer_block(name, reason, logo)}
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    if preset == LAYOUT_BOLD:
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head>
<body style="margin:0;padding:0;background:#111827;color:{_BODY_TEXT};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="background:{color};padding:28px;text-align:center;">
<p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;font-family:Arial,Helvetica,sans-serif;">{name}</p>
</td></tr>
<tr><td style="padding:32px 28px;color:{_BODY_TEXT};">{inner}</td></tr>
<tr><td style="padding:20px 28px 28px;background:#f9fafb;text-align:center;">
{_footer_block(name, reason, logo)}
</td></tr>
</table>
</td></tr></table>
</body></html>"""

    # classic (default) — centered store name in header, logo at bottom
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head>
<body style="margin:0;padding:0;background:#f8fafc;color:{_BODY_TEXT};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
<tr><td style="background:{color};padding:18px 24px;text-align:center;">
<p style="margin:0;font-size:16px;font-weight:600;color:#ffffff;">{name}</p>
</td></tr>
<tr><td style="padding:28px 28px;color:{_BODY_TEXT};">{inner}</td></tr>
<tr><td style="padding:20px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;text-align:center;">
{_footer_block(name, reason, logo)}
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
    # Skip missing files so outbound mail does not include a broken image.
    from pathlib import Path

    uploads = Path(__file__).resolve().parents[2] / "data" / "uploads" / "email-logos"
    if not (uploads / Path(path).name).is_file():
        return None
    base = app_url.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"
