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


def _pad_to_size(image, width: int, height: int):
    from PIL import Image, ImageOps

    rgb = image.convert("RGB")
    contained = ImageOps.contain(rgb, (width, height), method=Image.Resampling.LANCZOS)
    fill = rgb.getpixel((0, 0))
    if not isinstance(fill, tuple) or len(fill) < 3:
        fill = (255, 255, 255)
    canvas = Image.new("RGB", (width, height), fill[:3])
    canvas.paste(contained, ((width - contained.width) // 2, (height - contained.height) // 2))
    return canvas


def fit_image_bytes(
    data: bytes,
    width: int,
    height: int,
    *,
    fmt: str = "JPEG",
    mode: str = "cover",
) -> tuple[bytes, str]:
    """Resize so a still matches an API size exactly.

    cover: crop to fill (image edits). contain: letterbox so the whole SKU stays visible (video).
    """
    from PIL import Image, ImageOps

    image = Image.open(BytesIO(data))
    image = ImageOps.exif_transpose(image) or image
    if (mode or "cover").lower() == "contain":
        image = _pad_to_size(image, width, height)
    else:
        image = ImageOps.fit(
            image.convert("RGB"),
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    if image.size != (width, height):
        canvas = Image.new("RGB", (width, height), (255, 255, 255))
        canvas.paste(image, (0, 0))
        image = canvas
    buf = BytesIO()
    if (fmt or "JPEG").upper() == "PNG":
        image.save(buf, format="PNG", optimize=True)
        raw, mime = buf.getvalue(), "image/png"
    else:
        image.save(buf, format="JPEG", quality=92, subsampling=0)
        raw, mime = buf.getvalue(), "image/jpeg"
    verify = Image.open(BytesIO(raw))
    if verify.size != (width, height):
        raise ValueError(f"fitted still is {verify.size}, expected {(width, height)}")
    return raw, mime


def fit_references(
    references: list[tuple[bytes, str]] | None,
    size: str | None,
    *,
    fmt: str = "PNG",
    mode: str = "cover",
) -> list[tuple[bytes, str]]:
    dims = parse_wxh(size)
    out: list[tuple[bytes, str]] = []
    for raw, mime in references or []:
        if not raw:
            continue
        if not dims:
            continue
        try:
            out.append(fit_image_bytes(raw, dims[0], dims[1], fmt=fmt, mode=mode))
        except Exception as exc:
            logger.info("ai_ads identity fit skipped err=%s", exc)
    return out
