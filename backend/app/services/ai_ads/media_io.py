from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AppManagerAds/1.0)",
    "Accept": "image/jpeg,image/png,image/webp,image/*,*/*;q=0.8",
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


def _can_open_image(data: bytes) -> bool:
    try:
        from PIL import Image

        image = Image.open(BytesIO(data))
        image.load()
        image.close()
        return True
    except Exception:
        return False


def prefer_jpeg_url(url: str) -> str:
    """Ask Shopify CDN for a JPEG so Pillow can decode the still."""
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    if "shopify" not in host and "shopifysvc" not in host:
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["format"] = "jpg"
    query.setdefault("width", "1600")
    return urlunparse(parsed._replace(query=urlencode(query)))


async def fetch_image_bytes(url: str, *, timeout: float = 30) -> tuple[bytes, str] | None:
    src = (url or "").strip()
    if not src.startswith("http"):
        return None
    candidates = [src]
    jpeg_url = prefer_jpeg_url(src)
    if jpeg_url not in candidates:
        candidates.append(jpeg_url)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=_FETCH_HEADERS) as client:
            for candidate in candidates:
                try:
                    resp = await client.get(candidate)
                    resp.raise_for_status()
                except Exception as exc:
                    logger.info("ai_ads image fetch failed url=%s err=%s", candidate[:160], exc)
                    continue
                data = resp.content or b""
                if len(data) < 32 or not _can_open_image(data):
                    continue
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
    try:
        contained = ImageOps.contain(rgb, (width, height), method=Image.Resampling.LANCZOS)
    except TypeError:
        contained = ImageOps.contain(rgb, (width, height))
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
    image.load()
    image = ImageOps.exif_transpose(image) or image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        image = background
    else:
        image = image.convert("RGB")
    if (mode or "cover").lower() == "contain":
        image = _pad_to_size(image, width, height)
    else:
        image = ImageOps.fit(
            image,
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
        try:
            image.save(buf, format="JPEG", quality=92, subsampling=0)
        except Exception:
            buf = BytesIO()
            image.save(buf, format="JPEG", quality=90)
        raw, mime = buf.getvalue(), "image/jpeg"
    verify = Image.open(BytesIO(raw))
    verify.load()
    if verify.size != (width, height):
        raise ValueError(f"fitted still is {verify.size}, expected {(width, height)}")
    return raw, mime


def prepare_video_still(
    references: list[tuple[bytes, str]] | None,
    width: int,
    height: int,
) -> tuple[bytes, str]:
    """Return one Shopify still letterboxed to the video size, or raise."""
    errors: list[str] = []
    for raw, _mime in references or []:
        if not raw:
            continue
        for mode in ("contain", "cover"):
            try:
                return fit_image_bytes(raw, width, height, mode=mode)
            except Exception as exc:
                errors.append(f"{mode}:{exc}")
                logger.info("ai_ads video still fit skipped mode=%s err=%s", mode, exc)
    detail = "; ".join(errors[:3]) or "no product photos"
    raise ValueError(f"could not prepare a {width}x{height} product still ({detail})")


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
