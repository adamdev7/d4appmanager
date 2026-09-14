from __future__ import annotations

import base64
import logging
import re
from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    # Prefer JPEG/PNG. Advertising AVIF makes Shopify CDN return HEIF that stock
    # Pillow cannot decode even when format=jpg is on the URL.
    "Accept": "image/jpeg,image/jpg,image/png,image/webp;q=0.8,*/*;q=0.4",
}


def _enable_extra_decoders() -> None:
    """Shopify CDN often serves AVIF. Stock Pillow cannot open that."""
    try:
        import pillow_avif  # noqa: F401
    except Exception:
        pass
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass


_enable_extra_decoders()


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
    if len(data) > 12 and data[4:8] == b"ftyp" and b"avif" in data[:16].lower():
        return "image/avif"
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
    except Exception as exc:
        logger.info("ai_ads still not decodable mime=%s err=%s", sniff_image_mime(data), exc)
        return False


def normalize_image_url(url: str) -> str:
    src = (url or "").strip()
    if src.startswith("//"):
        src = "https:" + src
    return src


def prefer_jpeg_url(url: str) -> str:
    """Ask Shopify CDN for a JPEG so Pillow can decode the still."""
    parsed = urlparse(normalize_image_url(url))
    host = (parsed.netloc or "").lower()
    if "shopify" not in host and "shopifysvc" not in host:
        return normalize_image_url(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["format"] = "jpg"
    query.setdefault("width", "1400")
    return urlunparse(parsed._replace(query=urlencode(query)))


def _shopify_sized_path(url: str, suffix: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path or ""
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return None
    stem, ext = name.rsplit(".", 1)
    if re.search(r"_\d+x(\d+)?$", stem):
        return None
    new_name = f"{stem}_{suffix}.{ext}"
    new_path = path[: -len(name)] + new_name
    return urlunparse(parsed._replace(path=new_path))


def shopify_still_candidates(url: str) -> list[str]:
    src = normalize_image_url(url)
    if not src:
        return []
    out = [src]
    parsed = urlparse(src)
    host = (parsed.netloc or "").lower()
    if "shopify" not in host and "shopifysvc" not in host:
        return out
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for fmt in ("jpg", "pjpg", "png"):
        q = dict(query)
        q["format"] = fmt
        q.setdefault("width", "1400")
        out.append(urlunparse(parsed._replace(query=urlencode(q))))
    q = {k: v for k, v in query.items() if k != "format"}
    q["width"] = "1400"
    out.append(urlunparse(parsed._replace(query=urlencode(q))))
    for suffix in ("1024x1024", "1400x"):
        sized = _shopify_sized_path(src, suffix)
        if sized:
            out.append(sized)
            parsed_s = urlparse(sized)
            qs = dict(parse_qsl(parsed_s.query, keep_blank_values=True))
            qs["format"] = "jpg"
            out.append(urlunparse(parsed_s._replace(query=urlencode(qs))))
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def archive_image_bytes(data: bytes, *, max_side: int = 1400) -> tuple[bytes, str]:
    """Normalize a catalog still to a Pillow-safe JPEG suitable for reuse."""
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
    width, height = image.size
    longest = max(width, height)
    if longest > max_side > 0:
        scale = max_side / float(longest)
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )
    buf = BytesIO()
    try:
        image.save(buf, format="JPEG", quality=90, subsampling=0, optimize=True)
    except Exception:
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


def bytes_to_data_url(data: bytes, mime: str | None = None, *, max_side: int = 768) -> str:
    raw, out_mime = archive_image_bytes(data, max_side=max_side)
    kind = out_mime or mime or "image/jpeg"
    return f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"


async def fetch_image_bytes(
    url: str,
    *,
    timeout: float = 30,
    referer: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str] | None:
    src = normalize_image_url(url)
    if not src.startswith("http"):
        return None
    parsed = urlparse(src)
    headers = dict(_FETCH_HEADERS)
    if referer:
        headers["Referer"] = referer
    elif parsed.netloc:
        headers["Referer"] = f"https://{parsed.netloc}/"

    async def _try(http: httpx.AsyncClient) -> tuple[bytes, str] | None:
        for candidate in shopify_still_candidates(src):
            try:
                resp = await http.get(candidate, headers=headers)
                resp.raise_for_status()
            except Exception as exc:
                logger.info("ai_ads image fetch failed url=%s err=%s", candidate[:160], exc)
                continue
            data = resp.content or b""
            if len(data) < 32:
                continue
            if not _can_open_image(data):
                logger.info(
                    "ai_ads image undecodable url=%s ctype=%s magic=%s",
                    candidate[:160],
                    resp.headers.get("content-type"),
                    data[:16],
                )
                continue
            mime = sniff_image_mime(data, resp.headers.get("content-type"))
            return data, mime
        return None

    try:
        if client is not None:
            return await _try(client)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as owned:
            return await _try(owned)
    except Exception as exc:
        logger.info("ai_ads image fetch failed url=%s err=%s", src[:160], exc)
    return None


async def fetch_product_images(urls: list[str] | None, *, limit: int = 4) -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    seen: set[str] = set()
    for url in urls or []:
        if len(out) >= limit:
            break
        src = normalize_image_url(url)
        key = src.split("?")[0]
        if not key or key in seen:
            continue
        seen.add(key)
        got = await fetch_image_bytes(src)
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
