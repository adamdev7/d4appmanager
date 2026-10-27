"""Rebuild a picture from its pixels alone, then prove nothing else survived.

The output is never a patched copy of the upload: orientation and color profile are baked
into the pixels, the pixels are copied into a brand-new image with no metadata attached,
and that is encoded fresh. The result is rescanned with the same scanner used on the
upload and must contain only the bare pixel structure, or it is not returned at all.
"""

from __future__ import annotations

import base64
import math
import re
import secrets
from dataclasses import dataclass
from io import BytesIO
from pathlib import PureWindowsPath

from PIL import Image, ImageChops, ImageCms, ImageOps, ImageStat, UnidentifiedImageError

from app.core.upload_limits import MAX_UPLOAD_PART_BYTES
from app.services.md_cleaner.scanner import (
    ScanReport,
    filename_has_ai_hint,
    icc_description,
    scan_bytes,
)

OUTPUT_FORMATS = ("auto", "jpeg", "png")
MAX_INPUT_BYTES = MAX_UPLOAD_PART_BYTES
MAX_PIXELS = 60_000_000
JPEG_QUALITIES = (95, 94, 93)
MIN_JPEG_PSNR_DB = 38.0

_ALLOWED_STRUCTURE = {
    "jpeg": {"SOI", "APP0 JFIF", "DQT", "SOF0", "DHT", "SOS", "EOI"},
    "png": {"IHDR", "IDAT", "IEND"},
}
_ALLOWED_INFO = {
    "jpeg": {"jfif", "jfif_version", "jfif_unit", "jfif_density"},
    "png": set(),
}
_MIME = {"jpeg": "image/jpeg", "png": "image/png"}
_EXT = {"jpeg": "jpg", "png": "png"}


_TOO_MANY_PIXELS = "That picture has too many pixels to process safely (max 60 megapixels)."


class CleanError(ValueError):
    """User-facing reason a picture could not be cleaned."""


@dataclass
class CleanResult:
    data: bytes
    format: str
    filename: str
    width: int
    height: int
    before: ScanReport
    after: ScanReport
    fidelity: dict
    notes: list[str]
    passes: int

    @property
    def mime(self) -> str:
        return _MIME[self.format]

    def to_dict(self) -> dict:
        before = self.before.to_dict()
        return {
            "filename": self.filename,
            "mime": self.mime,
            "format": self.format,
            "width": self.width,
            "height": self.height,
            "size_bytes": len(self.data),
            "data_base64": base64.b64encode(self.data).decode("ascii"),
            "removed": before["findings"],
            "removed_count": len(before["findings"]),
            "meta_signals_removed": before["meta_signals"],
            "before": before,
            "after": self.after.to_dict(),
            "fidelity": self.fidelity,
            "notes": self.notes,
            "passes": self.passes,
        }


def clean_image(data: bytes, filename: str = "", output_format: str = "auto") -> CleanResult:
    if output_format not in OUTPUT_FORMATS:
        raise CleanError("Output format must be auto, jpeg or png.")
    if not data:
        raise CleanError("That file is empty.")
    if len(data) > MAX_INPUT_BYTES:
        raise CleanError("Pictures must be under 32 MB.")

    before = scan_bytes(data, filename)
    pixels, source_format, notes = _decode_to_pixels(data, before)
    has_alpha = pixels.mode == "RGBA"
    fmt = _pick_format(output_format, source_format, has_alpha)
    if fmt == "jpeg" and has_alpha:
        pixels = _flatten_on_white(pixels)
        notes.append("Transparent areas were filled with white because JPG has no transparency.")
    out_name = clean_filename(filename, fmt)

    problems: list[str] = []
    for attempt, quality in enumerate(JPEG_QUALITIES if fmt == "jpeg" else (None,), start=1):
        encoded = _encode(pixels, fmt, quality)
        after = scan_bytes(encoded, out_name)
        problems = _residue(after, fmt)
        if problems:
            continue
        fidelity, problems = _verify_pixels(pixels, encoded, fmt)
        if problems:
            continue
        return CleanResult(
            data=encoded,
            format=fmt,
            filename=out_name,
            width=pixels.width,
            height=pixels.height,
            before=before,
            after=after,
            fidelity=fidelity,
            notes=notes,
            passes=attempt,
        )
    raise CleanError(
        "The cleaned file did not pass the final check, so it was not released "
        f"({'; '.join(problems[:3])}). Try exporting the picture as PNG or JPG first."
    )


def clean_filename(original: str, fmt: str) -> str:
    stem = PureWindowsPath(original or "").stem
    stem = re.sub(r"[^\w\- ]+", "-", stem, flags=re.UNICODE)
    stem = re.sub(r"[\s\-]{2,}", "-", stem).strip(" -_.")[:80]
    if not stem or filename_has_ai_hint(stem):
        stem = f"image-{secrets.token_hex(4)}"
    return f"{stem}.{_EXT[fmt]}"


def _decode_to_pixels(data: bytes, before: ScanReport) -> tuple[Image.Image, str, list[str]]:
    notes: list[str] = []
    try:
        img = Image.open(BytesIO(data))
    except Image.DecompressionBombError as err:
        raise CleanError(_TOO_MANY_PIXELS) from err
    except (UnidentifiedImageError, OSError) as err:
        raise CleanError(
            "This file isn't a picture we can read. Use JPG, PNG, WebP, HEIC, AVIF, GIF, TIFF or BMP."
        ) from err

    with img:
        if img.width * img.height > MAX_PIXELS:
            raise CleanError(_TOO_MANY_PIXELS)
        source_format = (img.format or "").upper()
        frames = int(getattr(img, "n_frames", 1) or 1)
        if frames > 1:
            img.seek(0)
            if source_format in ("GIF", "PNG", "WEBP"):
                notes.append("Animated picture — only the first frame was kept (Meta image ads are still images).")
        try:
            img.load()
        except Exception as err:
            raise CleanError("The picture data is damaged and can't be decoded.") from err
        icc = img.info.get("icc_profile") if isinstance(img.info.get("icc_profile"), bytes) else None
        work = _apply_orientation(img, notes)

    work = _to_srgb(work, icc, notes)
    work = _normalize_mode(work)
    work = _clear_alpha_payload(work, before, notes)
    # A brand-new image has an empty info dict, so encoders have nothing to fall back on.
    clean = Image.new(work.mode, work.size)
    clean.paste(work)
    return clean, source_format, notes


def _apply_orientation(img: Image.Image, notes: list[str]) -> Image.Image:
    try:
        orientation = int(img.getexif().get(0x0112, 1) or 1)
    except Exception:
        orientation = 1
    try:
        turned = ImageOps.exif_transpose(img)
    except Exception:
        turned = None
    if turned is None:
        return img.copy()
    if orientation not in (0, 1):
        notes.append("The camera rotation tag was applied to the pixels so the picture stays upright.")
    return turned


def _to_srgb(img: Image.Image, icc: bytes | None, notes: list[str]) -> Image.Image:
    if not icc or len(icc) < 132:
        return img
    space = icc[16:20]
    desc = icc_description(icc) or ""
    if space == b"RGB " and "srgb" in desc.lower() and img.mode in ("RGB", "RGBA", "P", "PA"):
        return img
    try:
        src = ImageCms.ImageCmsProfile(BytesIO(icc))
        dst = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        intent = ImageCms.Intent.RELATIVE_COLORIMETRIC
        if space == b"RGB ":
            base = _normalize_mode(img)
            out = ImageCms.profileToProfile(base, src, dst, renderingIntent=intent, outputMode=base.mode)
            if base.mode == "RGBA" and out.mode == "RGBA":
                out.putalpha(base.getchannel("A"))
        elif space == b"CMYK" and img.mode == "CMYK":
            out = ImageCms.profileToProfile(img, src, dst, renderingIntent=intent, outputMode="RGB")
        elif space == b"GRAY" and img.mode in ("L", "LA"):
            alpha = img.getchannel("A") if img.mode == "LA" else None
            out = ImageCms.profileToProfile(img.convert("L"), src, dst, renderingIntent=intent, outputMode="RGB")
            if alpha is not None:
                out.putalpha(alpha)
        else:
            notes.append("The color profile didn't match the picture, so it was dropped without conversion.")
            return img
    except Exception:
        notes.append("The embedded color profile was unreadable, so it was dropped without conversion.")
        return img
    if out is None:
        return img
    notes.append(
        f"Colors were converted from “{desc or 'embedded profile'}” to standard sRGB so they look the same without a profile."
    )
    return out


def _normalize_mode(img: Image.Image) -> Image.Image:
    mode = img.mode
    has_key = "transparency" in img.info
    if mode == "RGBA":
        return img
    if mode == "RGB":
        return img.convert("RGBA") if has_key else img
    if mode in ("P", "PA", "LA", "La", "RGBa"):
        return img.convert("RGBA") if (mode != "P" or has_key) else img.convert("RGB")
    if mode in ("1", "L"):
        return img.convert("RGBA") if has_key else img.convert("RGB")
    if mode.startswith("I"):
        wide = img if mode == "I" else img.convert("I")
        _, high = wide.getextrema()
        if high > 255:
            wide = wide.point(lambda v: v * (1 / 256))
        return wide.convert("L").convert("RGB")
    if mode == "F":
        return img.convert("L").convert("RGB")
    try:
        return img.convert("RGB")
    except (ValueError, OSError) as err:
        raise CleanError(f"Pictures in {mode} color mode aren't supported. Export it as RGB first.") from err


def _clear_alpha_payload(img: Image.Image, before: ScanReport, notes: list[str]) -> Image.Image:
    if img.mode != "RGBA":
        return img
    alpha = img.getchannel("A")
    # Stealth payloads (NovelAI) toggle the low bit of opaque pixels between 254 and 255.
    flattened = alpha.point(lambda a: 255 if a >= 254 else a)
    if any(f.code == "stealth_alpha" for f in before.findings):
        notes.append("A prompt hidden in the transparency pixels was wiped.")
    low, _ = flattened.getextrema()
    if low == 255:
        return img.convert("RGB")
    out = img.copy()
    out.putalpha(flattened)
    return out


def _flatten_on_white(img: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", img.size, (255, 255, 255))
    canvas.paste(img, mask=img.getchannel("A"))
    return canvas


def _pick_format(requested: str, source_format: str, has_alpha: bool) -> str:
    if requested in ("jpeg", "png"):
        return requested
    if has_alpha or source_format == "PNG":
        return "png"
    return "jpeg"


def _encode(img: Image.Image, fmt: str, quality: int | None) -> bytes:
    buf = BytesIO()
    if fmt == "jpeg":
        img.save(buf, format="JPEG", quality=quality, subsampling=0, optimize=True)
    else:
        img.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def _residue(after: ScanReport, fmt: str) -> list[str]:
    problems = [f"{f.label} ({f.location})" for f in after.findings]
    extra = [s for s in after.structure if s not in _ALLOWED_STRUCTURE[fmt]]
    if extra:
        problems.append("unexpected blocks: " + ", ".join(sorted(set(extra))))
    return problems


def _verify_pixels(src: Image.Image, encoded: bytes, fmt: str) -> tuple[dict, list[str]]:
    with Image.open(BytesIO(encoded)) as out:
        out.load()
        extra_info = set(out.info) - _ALLOWED_INFO[fmt]
        if extra_info:
            return {}, ["decoder still sees: " + ", ".join(sorted(extra_info))]
        if out.size != src.size:
            return {}, ["size changed while encoding"]
        if int(getattr(out, "n_frames", 1) or 1) != 1:
            return {}, ["more than one image in the output"]
        if fmt == "png":
            decoded = out if out.mode == src.mode else out.convert(src.mode)
            if ImageChops.difference(decoded, src).getbbox() is not None:
                return {}, ["PNG pixels differ from the source"]
            return {"lossless": True, "psnr_db": None, "label": "Pixel-perfect"}, []
        decoded = out if out.mode == "RGB" else out.convert("RGB")
        stat = ImageStat.Stat(ImageChops.difference(src, decoded))
    mse = sum(stat.sum2) / (3 * src.width * src.height)
    psnr = math.inf if mse == 0 else 10 * math.log10(255**2 / mse)
    if psnr < MIN_JPEG_PSNR_DB:
        return {}, [f"quality check failed ({psnr:.1f} dB)"]
    label = "Visually identical" if psnr >= 42 else "Excellent"
    return {
        "lossless": False,
        "psnr_db": None if math.isinf(psnr) else round(psnr, 1),
        "label": label,
    }, []
