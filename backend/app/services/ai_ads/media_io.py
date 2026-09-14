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
    # format=pjpg returns JPEG only when the client does not also accept WebP/AVIF.
    "Accept": "image/jpeg,image/jpg",
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
    if declared.startswith("image/") and "svg" not in declared:
        return declared
    return "application/octet-stream"


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


# GraphQL preferredContentType: JPG turns foo.png into foo_1400x.png.jpg — those URLs stay WebP or 404.
_TRANSFORM_DOUBLE_EXT = re.compile(
    r"_(?:[1-9]\d{2,4})x(?:[1-9]\d{2,4})?(\.[A-Za-z0-9]+)\.jpe?g$",
    re.IGNORECASE,
)


def _is_shopify_image_host(url: str) -> bool:
    parsed = urlparse(normalize_image_url(url))
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    return "shopify" in host or "shopifysvc" in host or "/cdn/shop/" in path


def canonical_shopify_url(url: str) -> str:
    """Strip GraphQL transform filenames and keep only the CDN version query."""
    src = normalize_image_url(url)
    parsed = urlparse(src)
    directory, slash, name = (parsed.path or "").rpartition("/")
    if name:
        match = _TRANSFORM_DOUBLE_EXT.search(name)
        if match:
            name = _TRANSFORM_DOUBLE_EXT.sub(match.group(1), name)
            path = f"{directory}{slash}{name}" if slash else f"/{name}"
            parsed = parsed._replace(path=path)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    keep = {}
    if query.get("v"):
        keep["v"] = query["v"]
    return urlunparse(parsed._replace(query=urlencode(keep)))


def prefer_jpeg_url(url: str) -> str:
    """Ask Shopify CDN for a progressive JPEG. format=jpg is ignored and still returns WebP."""
    src = canonical_shopify_url(url) if _is_shopify_image_host(url) else normalize_image_url(url)
    if not _is_shopify_image_host(src):
        return src
    return _with_format(src, "pjpg")


def _with_format(url: str, fmt: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["format"] = fmt
    return urlunparse(parsed._replace(query=urlencode(query)))


def _shop_cdn_url(url: str, shop_domain: str | None, folder: str) -> str | None:
    host = (shop_domain or "").replace("https://", "").replace("http://", "").strip("/")
    if not host:
        return None
    parsed = urlparse(canonical_shopify_url(url))
    name = (parsed.path or "").rsplit("/", 1)[-1]
    if not name:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    path = f"https://{host}/cdn/shop/{folder}/{name}"
    if query.get("v"):
        path = f"{path}?v={query['v']}"
    return path


def shopify_still_candidates(url: str, *, shop_domain: str | None = None) -> list[str]:
    src = normalize_image_url(url)
    if not src:
        return []
    if not _is_shopify_image_host(src):
        return [src]
    canonical = canonical_shopify_url(src)
    out: list[str] = [_with_format(canonical, "pjpg")]
    shop_url = _shop_cdn_url(canonical, shop_domain, "files")
    if shop_url:
        out.append(_with_format(shop_url, "pjpg"))
    if src != canonical:
        out.append(_with_format(src, "pjpg"))
    out.append(canonical)
    if src != canonical:
        out.append(src)
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _flatten_to_rgb(image):
    from PIL import Image

    mode = image.mode
    if mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        mode = image.mode
    if mode in {"RGBA", "RGBa", "LA", "La", "PA"} or "transparency" in getattr(image, "info", {}):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if mode == "RGB":
        return image
    return image.convert("RGB")


def _jpeg_bytes(image, *, quality: int) -> bytes:
    buf = BytesIO()
    try:
        image.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    except Exception:
        buf = BytesIO()
        image.save(buf, format="JPEG", quality=max(68, quality - 6))
    return buf.getvalue()


def archive_image_bytes(data: bytes, *, max_side: int = 1400) -> tuple[bytes, str]:
    """Convert PNG/WebP/HEIC/JPEG to a compressed JPEG the rest of Astra can reuse."""
    from PIL import Image, ImageFile, ImageOps

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    if not data or len(data) < 24:
        raise ValueError("That file is empty.")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as err:
        raise ValueError("Could not open that picture. PNG, JPEG, WebP, and HEIC are supported.") from err
    try:
        image = ImageOps.exif_transpose(image) or image
    except Exception:
        pass
    image = _flatten_to_rgb(image)
    width, height = image.size
    longest = max(width, height)
    if longest > max_side > 0:
        scale = max_side / float(longest)
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )
    quality = 88
    raw = _jpeg_bytes(image, quality=quality)
    while len(raw) > 1_200_000 and quality > 68:
        quality -= 8
        raw = _jpeg_bytes(image, quality=quality)
    if len(raw) > 1_200_000:
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        raw = _jpeg_bytes(image, quality=78)
    if len(raw) < 32:
        raise ValueError("Could not compress that picture.")
    return raw, "image/jpeg"


def bytes_to_data_url(data: bytes, mime: str | None = None, *, max_side: int = 768) -> str:
    raw, out_mime = archive_image_bytes(data, max_side=max_side)
    kind = out_mime or mime or "image/jpeg"
    return f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"


async def fetch_image_bytes(
    url: str,
    *,
    timeout: float = 10,
    referer: str | None = None,
    shop_domain: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str] | None:
    src = normalize_image_url(url)
    if not src.startswith("http"):
        return None
    parsed = urlparse(src)
    headers = dict(_FETCH_HEADERS)
    if referer:
        headers["Referer"] = referer
    elif shop_domain:
        host = shop_domain.replace("https://", "").replace("http://", "").strip("/")
        headers["Referer"] = f"https://{host}/"
    elif parsed.netloc:
        headers["Referer"] = f"https://{parsed.netloc}/"
    fallback_headers = dict(headers)
    fallback_headers["Accept"] = "image/jpeg,image/jpg,image/png,image/webp,image/*,*/*;q=0.1"

    async def _try(http: httpx.AsyncClient) -> tuple[bytes, str] | None:
        for candidate in shopify_still_candidates(src, shop_domain=shop_domain):
            attempt_headers = fallback_headers if "format=" not in candidate else headers
            try:
                resp = await http.get(candidate, headers=attempt_headers, timeout=timeout)
                resp.raise_for_status()
            except Exception as exc:
                logger.info("ai_ads image fetch failed url=%s err=%s", candidate[:160], exc)
                continue
            data = resp.content or b""
            ctype = (resp.headers.get("content-type") or "").lower()
            if (
                len(data) < 32
                or ctype.startswith("text/")
                or data[:15].lower().startswith(b"<!doctype")
                or data[:6].lower().startswith(b"<html")
            ):
                continue
            if not _can_open_image(data):
                logger.info(
                    "ai_ads image undecodable url=%s ctype=%s magic=%s",
                    candidate[:160],
                    ctype,
                    data[:16],
                )
                continue
            try:
                return archive_image_bytes(data)
            except Exception:
                continue
        logger.warning("ai_ads image fetch exhausted url=%s", src[:160])
        return None

    try:
        if client is not None:
            return await _try(client)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as owned:
            return await _try(owned)
    except Exception as exc:
        logger.info("ai_ads image fetch failed url=%s err=%s", src[:160], exc)
    return None


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
