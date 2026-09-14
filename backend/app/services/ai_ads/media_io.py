from __future__ import annotations

import logging
from io import BytesIO

import httpx

logger = logging.getLogger(__name__)

_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AppManagerAds/1.0)",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def is_mp4(data: bytes | None) -> bool:
    raw = data or b""
    return len(raw) > 12 and raw[4:8] == b"ftyp"


def sniff_image_mime(data: bytes, declared: str | None = None) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    declared = (declared or "").split(";")[0].strip().lower()
    if declared.startswith("image/"):
        return declared
    return "image/jpeg"


async def fetch_image_bytes(url: str, *, timeout: float = 30) -> tuple[bytes, str] | None:
    src = (url or "").strip()
    if not src.startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=_FETCH_HEADERS) as client:
            resp = await client.get(src)
            resp.raise_for_status()
        data = resp.content or b""
        if len(data) < 32:
            return None
        mime = sniff_image_mime(data, resp.headers.get("content-type"))
        return data, mime
    except Exception as exc:
        logger.info("ai_ads image fetch failed url=%s err=%s", src[:160], exc)
        return None


async def fetch_product_images(urls: list[str] | None, *, limit: int = 4) -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    for url in urls or []:
        if len(out) >= limit:
            break
        key = (url or "").split("?")[0]
        if not key or key in seen:
            continue
        seen.add(key)
        got = await fetch_image_bytes(url)
        if got:
            out.append(got)
    return out


def parse_wxh(size: str | None) -> tuple[int, int] | None:
    try:
        w_s, h_s = (size or "").lower().replace(" ", "").split("x", 1)
        width, height = int(w_s), int(h_s)
    except Exception:
        return None
    if width < 1 or height < 1:
        return None
    return width, height


def fit_image_bytes(
    data: bytes,
    width: int,
    height: int,
    *,
    fmt: str = "JPEG",
) -> tuple[bytes, str]:
    """Center-crop and resize so a still matches an API size exactly."""
    from PIL import Image

    image = Image.open(BytesIO(data))
    target = width / max(height, 1)
    src = image.width / max(image.height, 1)
    if src > target:
        new_w = max(1, int(image.height * target))
        left = (image.width - new_w) // 2
        image = image.crop((left, 0, left + new_w, image.height))
    else:
        new_h = max(1, int(image.width / target))
        top = (image.height - new_h) // 2
        image = image.crop((0, top, image.width, top + new_h))
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    buf = BytesIO()
    if (fmt or "JPEG").upper() == "PNG":
        image = image.convert("RGBA")
        image.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    image = image.convert("RGB")
    image.save(buf, format="JPEG", quality=92)
    return buf.getvalue(), "image/jpeg"


def fit_references(
    references: list[tuple[bytes, str]] | None,
    size: str | None,
    *,
    fmt: str = "PNG",
) -> list[tuple[bytes, str]]:
    dims = parse_wxh(size)
    out: list[tuple[bytes, str]] = []
    for raw, mime in references or []:
        if not raw:
            continue
        if not dims:
            out.append((raw, mime))
            continue
        try:
            out.append(fit_image_bytes(raw, dims[0], dims[1], fmt=fmt))
        except Exception as exc:
            logger.info("ai_ads identity fit skipped err=%s", exc)
            out.append((raw, mime))
    return out
