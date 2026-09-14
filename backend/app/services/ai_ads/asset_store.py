from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from app.services.ai_ads.exceptions import ImageGenerationError

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_UPLOADS = _BACKEND_ROOT / "data" / "uploads" / "ai-ads"


class CreativeAssetStore:
    """Local hashed asset cache. Avoids re-downloading unchanged Meta creatives."""

    def __init__(self, store_id: str) -> None:
        self.store_id = store_id
        self.dir = _UPLOADS / store_id
        self.dir.mkdir(parents=True, exist_ok=True)

    def public_url(self, relative_path: str) -> str:
        return f"/uploads/{relative_path.replace(chr(92), '/')}"

    def relative(self, path: Path) -> str:
        uploads_root = _BACKEND_ROOT / "data" / "uploads"
        try:
            return path.relative_to(uploads_root).as_posix()
        except ValueError:
            return path.name

    def exists_hash(self, digest: str, ext: str = "bin") -> Path | None:
        candidate = self.dir / f"{digest}.{ext}"
        return candidate if candidate.is_file() else None

    def save_bytes(
        self,
        data: bytes,
        *,
        mime_type: str | None = None,
        prefix: str = "asset",
        known_hash: str | None = None,
    ) -> dict:
        if not data:
            raise ImageGenerationError("Empty asset bytes")
        digest = known_hash or hashlib.sha256(data).hexdigest()
        ext = _ext_for_mime(mime_type, data)
        path = self.dir / f"{prefix}_{digest[:24]}.{ext}"
        if not path.is_file():
            path.write_bytes(data)
        rel = self.relative(path)
        return {
            "hash": digest,
            "path": str(path),
            "relative_path": rel,
            "public_url": self.public_url(rel),
            "bytes": len(data),
            "ext": ext,
        }

    def resolve_path(self, relative_or_abs: str | None) -> Path | None:
        if not relative_or_abs:
            return None
        path = Path(relative_or_abs)
        if path.is_file():
            return path
        uploads_root = _BACKEND_ROOT / "data" / "uploads"
        cleaned = relative_or_abs.lstrip("/").removeprefix("uploads/")
        for candidate in (uploads_root / cleaned, self.dir / Path(relative_or_abs).name):
            if candidate.is_file():
                return candidate
        return None

    def read_bytes(self, relative_or_abs: str | None) -> tuple[bytes, str] | None:
        path = self.resolve_path(relative_or_abs)
        if not path:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() == ".mp4":
            mime = "video/mp4"
        return path.read_bytes(), mime

    def delete_local(self, relative_or_abs: str | None) -> bool:
        """Permanently remove a generated file if it belongs to this store's upload folder."""
        if not relative_or_abs:
            return False
        path = Path(relative_or_abs)
        if not path.is_file():
            uploads_root = _BACKEND_ROOT / "data" / "uploads"
            candidate = uploads_root / relative_or_abs.lstrip("/").removeprefix("uploads/")
            path = candidate if candidate.is_file() else self.dir / Path(relative_or_abs).name
        try:
            resolved = path.resolve()
            root = self.dir.resolve()
            if resolved.is_file() and resolved.is_relative_to(root):
                resolved.unlink()
                return True
        except OSError:
            return False
        return False

    def file_to_data_url(self, relative_or_abs: str) -> str | None:
        path = Path(relative_or_abs)
        if not path.is_file():
            candidate = _BACKEND_ROOT / "data" / "uploads" / relative_or_abs
            if candidate.is_file():
                path = candidate
            else:
                local = self.dir / Path(relative_or_abs).name
                if local.is_file():
                    path = local
                else:
                    return None
        raw = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        import base64

        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _ext_for_mime(mime: str | None, data: bytes) -> str:
    if mime:
        if "png" in mime:
            return "png"
        if "webp" in mime:
            return "webp"
        if "gif" in mime:
            return "gif"
        if "mp4" in mime:
            return "mp4"
        if "jpeg" in mime or "jpg" in mime:
            return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        return "mp4"
    return "bin"


def aspect_ratio_label(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    from math import gcd

    g = gcd(width, height)
    a, b = width // g, height // g
    # Snap common ad ratios
    ratio = width / height
    if abs(ratio - 1) < 0.05:
        return "1:1"
    if abs(ratio - 0.8) < 0.06:
        return "4:5"
    if abs(ratio - 9 / 16) < 0.06:
        return "9:16"
    if abs(ratio - 16 / 9) < 0.08:
        return "16:9"
    return f"{a}:{b}"


def safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:80]
