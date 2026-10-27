"""Byte-level provenance scanner: every place a picture can carry AI or origin metadata.

Meta's "AI info" label is driven by C2PA Content Credentials and the IPTC DigitalSourceType
field (in XMP or inside the C2PA manifest). Everything else a file can carry — EXIF, XMP,
IPTC IIM, PNG text chunks, comments, thumbnails, appended images, color-profile text, the
file name — is reported too, because any of it can name the generator or hold the prompt.

JPEG, PNG and WebP are walked segment by segment. Other containers (HEIC, AVIF, GIF, TIFF,
BMP) are inspected through the decoder's metadata plus a raw signature sweep over every byte.
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PureWindowsPath

from PIL import ExifTags, Image


def _enable_extra_decoders() -> None:
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

CRITICAL = "critical"
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
_RANK = {CRITICAL: 3, HIGH: 2, MEDIUM: 1, LOW: 0}

MAX_PIXEL_CHECK = 40_000_000
_MAX_INFLATE = 8 * 1024 * 1024

# (check id, label, finding codes). Order is the order the UI shows the rescan checklist.
CHECKS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("c2pa", "Content Credentials (C2PA)", frozenset({"c2pa_manifest", "c2pa_reference"})),
    ("iptc_ai", "IPTC “AI-generated” source type", frozenset({"iptc_digital_source_type"})),
    (
        "ai_text",
        "AI tool names, prompts & settings",
        frozenset({"ai_tool_reference", "generation_parameters", "stealth_alpha"}),
    ),
    ("metadata", "EXIF, XMP & IPTC metadata", frozenset({"exif", "xmp", "iptc_iim", "photoshop_irb"})),
    (
        "hidden",
        "Comments, thumbnails & hidden extras",
        frozenset(
            {
                "comment",
                "text_chunk",
                "thumbnail",
                "extra_images",
                "trailing_data",
                "icc_profile",
                "timestamp",
                "display_hints",
            }
        ),
    ),
    ("filename", "Neutral file name", frozenset({"filename_hint"})),
    ("structure", "Clean file structure", frozenset({"unknown_block", "malformed"})),
)
_KNOWN_CODES = frozenset().union(*(codes for _, _, codes in CHECKS))

_AI_TOOLS: tuple[tuple[str, str], ...] = (
    ("OpenAI", r"open\s?ai|chat\s?gpt|\bdall[\s\-_·.]*e\b|gpt[\s\-_]?4o|gpt[\s\-_]?image|\bsora\b"),
    ("Midjourney", r"mid\s?journey|\bniji\b"),
    (
        "Stable Diffusion",
        r"stable[\s\-_]?diffusion|stability[\s.]?ai|\bsdxl\b|\bsd[\s_]?3(?:\.5)?\b|dreamstudio|automatic1111|\binvoke\s?ai\b",
    ),
    ("ComfyUI", r"comfy\s?ui"),
    ("NovelAI", r"novel\s?ai"),
    ("Adobe Firefly", r"\bfirefly\b|generative\s(?:fill|expand)"),
    ("Google AI", r"made with google ai|google\s?imagen|\bimagen\s?[1-9]\b|\bgemini\b|synth\s?id|nano[\s\-_]?banana"),
    ("Microsoft", r"bing image creator|microsoft designer|\bimage creator\b|\bcopilot\b"),
    ("Meta AI", r"imagine with meta|imagined with ai|\bmeta ai\b"),
    ("Flux", r"\bflux(?:\.1)?\b|black\s?forest\s?labs"),
    ("Ideogram", r"ideogram"),
    ("Leonardo", r"leonardo[\s.]?ai"),
    ("Runway", r"runway\s?ml|runway gen"),
    ("Krea", r"\bkrea\b"),
    ("Playground", r"playground\s?ai|playground\sv\d"),
    ("Recraft", r"recraft"),
    ("Canva AI", r"canva\s?ai|magic media|dream lab"),
    ("Grok / xAI", r"\bgrok\b|\bx\.ai\b"),
    ("Freepik AI", r"freepik\s?ai|\bpikaso\b"),
    ("Civitai / Tensor.Art", r"civitai|tensor\.art"),
    ("ByteDance", r"seedream|dreamina|\bjimeng\b|doubao"),
    ("Kling", r"\bkling\b"),
    ("Hunyuan", r"hunyuan"),
    ("Qwen", r"\bqwen\b"),
    ("NightCafe", r"nightcafe"),
    ("Artbreeder", r"artbreeder"),
    ("Picsart AI", r"picsart\s?ai"),
    ("AIGC label", r"\baigc\b|tc260"),
    ("Generic AI mark", r"ai[\s\-_]generated|generated (?:by|with) ai|\bgenai\b|generative ai"),
)
_AI_TOOL_RES = tuple((name, re.compile(pattern, re.I | re.A)) for name, pattern in _AI_TOOLS)

_GEN_PARAMS_RE = re.compile(
    r"negative prompt|\bsampler\b|cfg scale|\bsteps:\s*\d|\bseed:\s*\d|model hash|denoising strength"
    r"|\blora\b|\"class_type\"|ckpt_name|--ar\s\d|--v\s\d|--style\sraw|\bjob id\b|\bprompt\":",
    re.I | re.A,
)
_PRINTABLE_RUN = re.compile(rb"[\x20-\x7e\t\r\n]{4,}")
_GEN_KEYS = frozenset(
    {
        "parameters",
        "prompt",
        "workflow",
        "dream",
        "sd-metadata",
        "invokeai_metadata",
        "invokeai_graph",
        "generation_data",
        "negative_prompt",
        "aigc",
    }
)

_AI_DST_RE = re.compile(
    r"\b(compositeWithTrainedAlgorithmicMedia|trainedAlgorithmicMedia|algorithmicMedia"
    r"|compositeSynthetic|algorithmicallyEnhanced)\b",
    re.I | re.A,
)
_DST_RE = re.compile(r"digitalsourcetype/([A-Za-z]+)", re.I | re.A)

_C2PA_BMFF_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")

# Raw sweep literals. Searched with bytes.find (memchr-fast) rather than regex alternation,
# which is ~20x slower on 30 MB uploads. Tool and source-type terms are matched lowercase.
_RAW_C2PA = (
    b"jumdc2pa",
    b"c2pa.claim",
    b"c2pa.assertions",
    b"c2pa.signature",
    b"c2pa.actions",
    b"c2pa.hash",
    b"C2PA_GIF",
    _C2PA_BMFF_UUID,
)
_RAW_XMP = (b"<x:xmpmeta", b"<?xpacket", b"http://ns.adobe.com/xap/1.0/")
_RAW_EXIF = (b"Exif\x00\x00II*\x00", b"Exif\x00\x00MM\x00*")
_RAW_IRB = (b"Photoshop 3.0\x00", b"8BIM\x04\x04")
_RAW_DST = (b"algorithmicmedia", b"compositesynthetic", b"algorithmicallyenhanced", b"digitalsourcetype/")
_RAW_TOOLS = (
    b"midjourney",
    b"openai",
    b"chatgpt",
    b"dall-e",
    "dall·e".encode(),
    b"stable diffusion",
    b"stablediffusion",
    b"comfyui",
    b"automatic1111",
    b"novelai",
    b"firefly",
    b"made with google ai",
    b"synthid",
    b"imagine with meta",
    b"ideogram",
    b"leonardo.ai",
    b"black forest labs",
)

_UUID_RE = re.compile(r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.I)
_FILENAME_HINT_RE = re.compile(r"generated|\bai[\s_\-]?(?:image|art|photo)\b", re.I)

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_PNG_STRUCTURAL = {"IHDR", "PLTE", "IDAT", "IEND", "tRNS", "acTL", "fcTL", "fdAT"}
_PNG_DISPLAY = {"gAMA", "cHRM", "sRGB", "sBIT", "bKGD", "pHYs", "hIST", "sPLT", "cICP", "mDCV", "cLLI"}
_WEBP_STRUCTURAL = {"VP8 ", "VP8L", "VP8X", "ALPH", "ANIM", "ANMF"}
_BMFF_STRUCTURAL = {"ftyp", "meta", "mdat", "moov", "free", "skip", "wide"}

_EXIF_TEXT_TAGS = {
    0x010E: "ImageDescription",
    0x010F: "Make",
    0x0110: "Model",
    0x0131: "Software",
    0x013B: "Artist",
    0x013C: "HostComputer",
    0x8298: "Copyright",
    0x9C9B: "XPTitle",
    0x9C9C: "XPComment",
    0x9C9D: "XPAuthor",
    0x9C9E: "XPKeywords",
    0x9C9F: "XPSubject",
}
_EXIF_SUB_TEXT_TAGS = {
    0x9286: "UserComment",
    0xA420: "ImageUniqueID",
    0xA430: "CameraOwnerName",
    0xA431: "BodySerialNumber",
    0xA433: "LensMake",
    0xA434: "LensModel",
}
_XMP_FIELDS = (
    "xmp:CreatorTool",
    "Iptc4xmpExt:DigitalSourceType",
    "photoshop:Credit",
    "photoshop:Source",
    "dc:creator",
    "dc:description",
    "dc:title",
    "tiff:Software",
    "xmpMM:DocumentID",
)
_IIM_FIELDS = {
    5: "Title",
    25: "Keywords",
    65: "Originating program",
    70: "Program version",
    80: "By-line",
    110: "Credit",
    115: "Source",
    116: "Copyright",
    120: "Caption",
    122: "Writer",
}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    label: str
    detail: str
    location: str
    meta_signal: bool = False

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "label": self.label,
            "detail": self.detail,
            "location": self.location,
            "meta_signal": self.meta_signal,
        }


@dataclass
class ScanReport:
    container: str
    filename: str
    size_bytes: int
    findings: list[Finding] = field(default_factory=list)
    structure: list[str] = field(default_factory=list)
    image: dict | None = None

    @property
    def verdict(self) -> str:
        if any(f.severity == CRITICAL for f in self.findings):
            return "ai_labeled"
        if any(f.severity == HIGH for f in self.findings):
            return "ai_traces"
        if self.findings:
            return "metadata"
        return "clean"

    def checks(self) -> list[dict]:
        rows = []
        for check_id, label, codes in CHECKS:
            hits = [
                f
                for f in self.findings
                if f.code in codes or (check_id == "structure" and f.code not in _KNOWN_CODES)
            ]
            rows.append({"id": check_id, "label": label, "passed": not hits, "count": len(hits)})
        return rows

    def to_dict(self) -> dict:
        ordered = sorted(self.findings, key=lambda f: (-_RANK.get(f.severity, 0), f.code))
        return {
            "verdict": self.verdict,
            "container": self.container,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "image": self.image,
            "meta_signals": sum(1 for f in self.findings if f.meta_signal),
            "findings": [f.to_dict() for f in ordered],
            "checks": self.checks(),
            "structure": self.structure,
        }


def scan_bytes(data: bytes, filename: str = "") -> ScanReport:
    return _Scanner(data, filename).run()


def filename_has_ai_hint(name: str) -> bool:
    stem = (name or "").replace("_", " ")
    return bool(
        _tool_names(stem) or _FILENAME_HINT_RE.search(stem) or _UUID_RE.search(stem)
    )


def icc_description(profile: bytes) -> str | None:
    texts = _icc_texts(profile)
    return texts.get("desc")


def container_of(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        return "heif"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:2] == b"BM":
        return "bmp"
    return "unknown"


def _tool_names(text: str) -> list[str]:
    return [name for name, rx in _AI_TOOL_RES if rx.search(text)]


def _decode(raw: bytes) -> str:
    if not raw:
        return ""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16").replace("\x00", "")
        except UnicodeDecodeError:
            pass
    if raw.count(b"\x00") > len(raw) // 3:
        try:
            return raw.decode("utf-16-le").replace("\x00", "")
        except UnicodeDecodeError:
            pass
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text.replace("\x00", "")


def _printable(raw: bytes) -> str:
    """Text runs inside a binary blob, so random bytes can't spell out a tool name."""
    return "\n".join(run.decode("ascii") for run in _PRINTABLE_RUN.findall(raw))


def _excerpt(text: str, at: int = 0, width: int = 90) -> str:
    start = max(0, at - width // 3)
    snippet = " ".join(text[start : start + width].split())
    if start > 0:
        snippet = "…" + snippet
    if start + width < len(text):
        snippet += "…"
    return snippet


def _inflate(blob: bytes) -> bytes:
    try:
        return zlib.decompressobj().decompress(blob, _MAX_INFLATE)
    except zlib.error:
        return b""


def _icc_texts(profile: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        (count,) = struct.unpack(">I", profile[128:132])
        for i in range(min(count, 128)):
            base = 132 + 12 * i
            sig, offset, size = struct.unpack(">4sII", profile[base : base + 12])
            name = sig.decode("latin-1")
            if name not in ("desc", "cprt", "dmnd", "dmdd"):
                continue
            blob = profile[offset : offset + size]
            text = _icc_tag_text(blob)
            if text:
                out[name] = text
    except (struct.error, IndexError):
        pass
    return out


def _icc_tag_text(blob: bytes) -> str | None:
    kind = blob[:4]
    try:
        if kind == b"desc":
            (n,) = struct.unpack(">I", blob[8:12])
            return blob[12 : 12 + n].rstrip(b"\x00").decode("latin-1").strip() or None
        if kind == b"text":
            return blob[8:].rstrip(b"\x00").decode("latin-1").strip() or None
        if kind == b"mluc":
            (records,) = struct.unpack(">I", blob[8:12])
            if records < 1:
                return None
            length, offset = struct.unpack(">II", blob[20:28])
            return blob[offset : offset + length].decode("utf-16-be").strip() or None
    except (struct.error, UnicodeDecodeError):
        return None
    return None


class _Scanner:
    def __init__(self, data: bytes, filename: str) -> None:
        self.data = data
        self.filename = filename or ""
        self.container = container_of(data)
        self.findings: list[Finding] = []
        self.structure: list[str] = []
        self._seen: set[tuple[str, str, str]] = set()
        self._icc_chunks: list[tuple[int, bytes]] = []
        self._jumbf_chunks: list[bytes] = []

    def run(self) -> ScanReport:
        walker = {
            "jpeg": self._walk_jpeg,
            "png": self._walk_png,
            "webp": self._walk_webp,
            "heif": self._walk_bmff,
            "avif": self._walk_bmff,
        }.get(self.container)
        if walker:
            try:
                walker()
            except (struct.error, IndexError, ValueError) as err:
                self._add("malformed", MEDIUM, "File structure is damaged", str(err)[:120], self.container)
        else:
            self.structure.append(self.container.upper())
        image = self._inspect_decoded(trust_walker=self.container in ("jpeg", "png", "webp"))
        self._raw_sweep()
        self._inspect_filename()
        return ScanReport(
            container=self.container,
            filename=self.filename,
            size_bytes=len(self.data),
            findings=self.findings,
            structure=self.structure,
            image=image,
        )

    def _add(
        self,
        code: str,
        severity: str,
        label: str,
        detail: str,
        location: str,
        meta_signal: bool = False,
    ) -> None:
        key = (code, label, location)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append(Finding(code, severity, label, detail, location, meta_signal))

    def _has(self, code: str, label: str | None = None) -> bool:
        return any(f.code == code and (label is None or f.label == label) for f in self.findings)

    # ---- content inspectors -------------------------------------------------------------

    def _inspect_text(self, text: str, location: str) -> None:
        if not text:
            return
        for name, rx in _AI_TOOL_RES:
            match = rx.search(text)
            if match and not self._has("ai_tool_reference", f"Names {name}"):
                self._add(
                    "ai_tool_reference",
                    HIGH,
                    f"Names {name}",
                    f"“{_excerpt(text, match.start())}”",
                    location,
                )
        match = _GEN_PARAMS_RE.search(text)
        if match:
            self._add(
                "generation_parameters",
                HIGH,
                "AI prompt or generation settings",
                f"“{_excerpt(text, match.start())}”",
                location,
            )
        self._inspect_dst(text, location)

    def _inspect_dst(self, text: str, location: str) -> None:
        ai_values = sorted({m.group(1) for m in _AI_DST_RE.finditer(text)}, key=str.lower)
        if ai_values:
            self._add(
                "iptc_digital_source_type",
                CRITICAL,
                "Source type says “AI-generated”",
                f"DigitalSourceType = {', '.join(ai_values)}",
                location,
                meta_signal=True,
            )
            return
        other = sorted({m.group(1) for m in _DST_RE.finditer(text)})
        if other:
            self._add(
                "iptc_digital_source_type",
                MEDIUM,
                "Source type declared",
                f"DigitalSourceType = {', '.join(other)}",
                location,
                meta_signal=True,
            )

    def _inspect_c2pa(self, blob: bytes, location: str) -> None:
        text = _printable(blob)
        parts: list[str] = []
        if _AI_DST_RE.search(text):
            parts.append("declares the picture AI-generated")
        generator = _c2pa_generator(blob)
        if generator:
            parts.append(f"signed by “{generator}”")
        tools = _tool_names(text)
        if tools:
            parts.append("made with " + ", ".join(tools[:3]))
        self._add(
            "c2pa_manifest",
            CRITICAL,
            "Content Credentials (C2PA)",
            "; ".join(parts) or f"{len(blob):,} bytes of signed provenance data",
            location,
            meta_signal=True,
        )

    def _inspect_xmp(self, xml: bytes, location: str) -> None:
        text = _decode(xml)
        fields: list[str] = []
        for key in _XMP_FIELDS:
            value = _xmp_value(text, key)
            if value:
                fields.append(f"{key.split(':', 1)[1]}: {value[:60]}")
        if "jumbf=" in text or "c2pa" in text.lower():
            self._add(
                "c2pa_reference",
                HIGH,
                "Link to Content Credentials",
                "XMP points to a C2PA manifest",
                location,
            )
        self._add(
            "xmp",
            MEDIUM,
            "XMP metadata",
            "; ".join(fields[:5]) or f"{len(xml):,} bytes",
            location,
        )
        self._inspect_text(text, location)

    def _inspect_exif(self, payload: bytes, location: str) -> None:
        fields: list[str] = []
        count = 0
        try:
            exif = Image.Exif()
            exif.load(payload)
            count = len(exif)
            for tag, name in _EXIF_TEXT_TAGS.items():
                value = _exif_text(exif.get(tag))
                if value:
                    fields.append(f"{name}: {value[:60]}")
                    self._inspect_text(value, f"{location} · {name}")
            sub = exif.get_ifd(ExifTags.IFD.Exif)
            count += len(sub)
            for tag, name in _EXIF_SUB_TEXT_TAGS.items():
                value = _exif_text(sub.get(tag))
                if value:
                    fields.append(f"{name}: {value[:60]}")
                    self._inspect_text(value, f"{location} · {name}")
            if 0x927C in sub:
                fields.append("MakerNote")
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            if gps:
                count += len(gps)
                fields.append("GPS location")
        except Exception:
            fields.append("unreadable block")
        self._add(
            "exif",
            MEDIUM,
            "EXIF metadata",
            f"{count} fields" + (f" — {'; '.join(fields[:6])}" if fields else ""),
            location,
        )
        tiff = payload[6:] if payload.startswith(b"Exif\x00\x00") else payload
        if tiff.find(b"\xff\xd8\xff", 8) != -1:
            self._add(
                "thumbnail",
                MEDIUM,
                "Embedded preview thumbnail",
                "A second, smaller copy of the picture lives inside the EXIF block",
                location,
            )

    def _inspect_icc(self, profile: bytes, location: str) -> None:
        texts = _icc_texts(profile)
        self._add(
            "icc_profile",
            LOW,
            "Embedded color profile",
            texts.get("desc") or f"{len(profile):,} bytes",
            location,
        )
        for name, value in texts.items():
            self._inspect_text(value, f"{location} · {name}")

    def _inspect_irb(self, payload: bytes, location: str) -> None:
        pos = 0
        resources = 0
        while pos + 12 <= len(payload) and payload[pos : pos + 4] == b"8BIM":
            (rid,) = struct.unpack(">H", payload[pos + 4 : pos + 6])
            name_len = payload[pos + 6]
            name_total = 1 + name_len + ((1 + name_len) % 2)
            size_at = pos + 6 + name_total
            (size,) = struct.unpack(">I", payload[size_at : size_at + 4])
            body = payload[size_at + 4 : size_at + 4 + size]
            pos = size_at + 4 + size + (size % 2)
            resources += 1
            if rid == 0x0404:
                self._inspect_iim(body, f"{location} · IPTC")
            elif rid in (0x0409, 0x040C):
                self._add("thumbnail", MEDIUM, "Embedded preview thumbnail", "Photoshop thumbnail", location)
            elif rid == 0x0422:
                self._inspect_exif(body, f"{location} · EXIF")
            elif rid == 0x0424:
                self._inspect_xmp(body, f"{location} · XMP")
            elif rid == 0x040F:
                self._inspect_icc(body, f"{location} · ICC")
            else:
                self._inspect_text(_printable(body[:262144]), location)
        self._add(
            "photoshop_irb",
            MEDIUM,
            "Photoshop / IPTC block",
            f"{resources} resource{'s' if resources != 1 else ''}",
            location,
        )

    def _inspect_iim(self, body: bytes, location: str) -> None:
        pos = 0
        fields: list[str] = []
        while pos + 5 <= len(body) and body[pos] == 0x1C:
            record, dataset = body[pos + 1], body[pos + 2]
            (size,) = struct.unpack(">H", body[pos + 3 : pos + 5])
            pos += 5
            if size & 0x8000:
                n = size & 0x7FFF
                size = int.from_bytes(body[pos : pos + n], "big")
                pos += n
            value = _decode(body[pos : pos + size]).strip()
            pos += size
            if record == 2 and dataset in _IIM_FIELDS and value:
                fields.append(f"{_IIM_FIELDS[dataset]}: {value[:60]}")
                self._inspect_text(value, f"{location} · {_IIM_FIELDS[dataset]}")
        self._add(
            "iptc_iim",
            MEDIUM,
            "IPTC metadata",
            "; ".join(fields[:5]) or "IPTC record",
            location,
        )

    def _inspect_text_chunk(self, key: str, value: str, location: str) -> None:
        lowered = key.lower()
        if key == "XML:com.adobe.xmp":
            self._inspect_xmp(value.encode("utf-8"), location)
            return
        if lowered.startswith("raw profile type "):
            kind = lowered.rsplit(" ", 1)[-1]
            blob = _imagemagick_profile(value)
            if kind in ("exif", "app1") and blob:
                self._inspect_exif(blob, location)
                return
            if kind == "xmp" and blob:
                self._inspect_xmp(blob, location)
                return
            if kind in ("iptc", "8bim") and blob:
                start = blob.find(b"8BIM")
                if start != -1:
                    self._inspect_irb(blob[start:], location)
                    return
        if lowered in _GEN_KEYS or _GEN_PARAMS_RE.search(value):
            self._add(
                "generation_parameters",
                HIGH,
                "AI prompt or generation settings",
                f"{key}: “{_excerpt(value)}”",
                location,
            )
        else:
            self._add("text_chunk", MEDIUM, f"Text field “{key[:40]}”", f"“{_excerpt(value)}”", location)
        self._inspect_text(f"{key} {value}", location)

    # ---- container walkers --------------------------------------------------------------

    def _walk_jpeg(self) -> None:
        data = self.data
        self.structure.append("SOI")
        pos = 2
        end = len(data)
        eoi = None
        while pos < end:
            if data[pos] != 0xFF:
                raise ValueError(f"unexpected byte at offset {pos}")
            while pos < end and data[pos] == 0xFF:
                pos += 1
            if pos >= end:
                break
            marker = data[pos]
            pos += 1
            if marker == 0xD9:
                self.structure.append("EOI")
                eoi = pos
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            (length,) = struct.unpack(">H", data[pos : pos + 2])
            if length < 2 or pos + length > end:
                raise ValueError(f"segment 0x{marker:02X} runs past the end of the file")
            payload = data[pos + 2 : pos + length]
            pos += length
            self._jpeg_segment(marker, payload)
            if marker == 0xDA:
                pos = _skip_entropy(data, pos)
        self._finish_icc("JPEG APP2")
        if self._jumbf_chunks:
            manifest = b"".join(self._jumbf_chunks)
            if b"c2pa" in manifest or b"jumd" in manifest:
                self._inspect_c2pa(manifest, "JPEG APP11")
            else:
                self._add("unknown_block", MEDIUM, "Unknown APP11 block", f"{len(manifest):,} bytes", "JPEG APP11")
        if eoi is None:
            self._add("malformed", MEDIUM, "File structure is damaged", "No end-of-image marker", "JPEG")
            return
        self._trailing(data[eoi:], "after JPEG end marker")

    def _jpeg_segment(self, marker: int, payload: bytes) -> None:
        name = f"APP{marker - 0xE0}" if 0xE0 <= marker <= 0xEF else None
        if marker in _JPEG_SOF:
            self.structure.append(f"SOF{marker - 0xC0}")
        elif marker == 0xC4:
            self.structure.append("DHT")
        elif marker == 0xDB:
            self.structure.append("DQT")
        elif marker == 0xDD:
            self.structure.append("DRI")
        elif marker == 0xDA:
            self.structure.append("SOS")
        elif marker == 0xDC:
            self.structure.append("DNL")
        elif marker == 0xFE:
            self.structure.append("COM")
            text = _decode(payload)
            self._add("comment", MEDIUM, "Hidden comment", f"“{_excerpt(text)}”", "JPEG comment")
            self._inspect_text(text, "JPEG comment")
        elif marker == 0xE0 and payload.startswith(b"JFIF\x00"):
            self.structure.append("APP0 JFIF")
            if len(payload) >= 14 and payload[12] * payload[13] > 0:
                self._add("thumbnail", MEDIUM, "Embedded preview thumbnail", "JFIF thumbnail", "JPEG APP0")
        elif marker == 0xE0 and payload.startswith(b"JFXX\x00"):
            self.structure.append("APP0 JFXX")
            self._add("thumbnail", MEDIUM, "Embedded preview thumbnail", "JFXX thumbnail", "JPEG APP0")
        elif marker == 0xE1 and payload.startswith(b"Exif\x00"):
            self.structure.append("APP1 Exif")
            self._inspect_exif(payload, "JPEG APP1 EXIF")
        elif marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
            self.structure.append("APP1 XMP")
            self._inspect_xmp(payload[29:], "JPEG APP1 XMP")
        elif marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xmp/extension/\x00"):
            self.structure.append("APP1 XMP extension")
            self._inspect_xmp(payload[35 + 40 :], "JPEG APP1 extended XMP")
        elif marker == 0xE2 and payload.startswith(b"ICC_PROFILE\x00"):
            self.structure.append("APP2 ICC")
            if len(payload) >= 14:
                self._icc_chunks.append((payload[12], payload[14:]))
        elif marker == 0xE2 and payload.startswith(b"MPF\x00"):
            self.structure.append("APP2 MPF")
            self._add(
                "extra_images",
                MEDIUM,
                "Extra embedded images",
                "Multi-picture index (depth map, HDR gain map, or original copy)",
                "JPEG APP2 MPF",
            )
        elif marker == 0xEB:
            self.structure.append("APP11 JUMBF")
            self._jumbf_chunks.append(payload)
        elif marker == 0xED and payload.startswith(b"Photoshop 3.0\x00"):
            self.structure.append("APP13 Photoshop")
            self._inspect_irb(payload[14:], "JPEG APP13")
        elif marker == 0xEE and payload.startswith(b"Adobe"):
            self.structure.append("APP14 Adobe")
        elif name:
            tag = payload[:16].split(b"\x00", 1)[0].decode("latin-1", "replace")
            self.structure.append(f"{name} {tag}".strip())
            self._add("unknown_block", MEDIUM, f"Extra {name} block", tag or f"{len(payload):,} bytes", f"JPEG {name}")
            self._inspect_text(_printable(payload[:262144]), f"JPEG {name}")
        else:
            self.structure.append(f"0x{marker:02X}")
            self._add("unknown_block", MEDIUM, "Unknown JPEG segment", f"marker 0x{marker:02X}", "JPEG")

    def _finish_icc(self, location: str) -> None:
        if not self._icc_chunks:
            return
        profile = b"".join(chunk for _, chunk in sorted(self._icc_chunks, key=lambda c: c[0]))
        self._inspect_icc(profile, location)

    def _walk_png(self) -> None:
        data = self.data
        pos = 8
        end = len(data)
        display: list[str] = []
        while pos + 8 <= end:
            length, ctype_raw = struct.unpack(">I4s", data[pos : pos + 8])
            ctype = ctype_raw.decode("latin-1")
            body = data[pos + 8 : pos + 8 + length]
            if pos + 12 + length > end:
                raise ValueError(f"chunk {ctype!r} runs past the end of the file")
            pos += 12 + length
            self.structure.append(ctype)
            location = f"PNG {ctype}"
            if ctype == "IEND":
                self._trailing(data[pos:], "after PNG end chunk")
                break
            if ctype in _PNG_STRUCTURAL:
                continue
            if ctype in _PNG_DISPLAY:
                display.append(ctype)
            elif ctype == "tEXt":
                key, _, value = body.partition(b"\x00")
                self._inspect_text_chunk(key.decode("latin-1"), value.decode("latin-1"), location)
            elif ctype == "zTXt":
                key, _, rest = body.partition(b"\x00")
                self._inspect_text_chunk(key.decode("latin-1"), _decode(_inflate(rest[1:])), location)
            elif ctype == "iTXt":
                key, _, rest = body.partition(b"\x00")
                compressed = rest[:1] == b"\x01"
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\x00")
                _tkey, _, text = rest.partition(b"\x00")
                if compressed:
                    text = _inflate(text)
                self._inspect_text_chunk(key.decode("latin-1"), _decode(text), location)
            elif ctype == "eXIf":
                self._inspect_exif(body, location)
            elif ctype == "iCCP":
                name, _, rest = body.partition(b"\x00")
                self._inspect_icc(_inflate(rest[1:]), location)
            elif ctype == "caBX":
                self._inspect_c2pa(body, location)
            elif ctype == "tIME":
                self._add("timestamp", LOW, "Last-modified timestamp", "PNG tIME chunk", location)
            else:
                self._add("unknown_block", MEDIUM, f"Unknown PNG chunk “{ctype}”", f"{length:,} bytes", location)
                self._inspect_text(_printable(body[:262144]), location)
        if display:
            self._add(
                "display_hints",
                LOW,
                "Display hints",
                ", ".join(sorted(set(display))),
                "PNG",
            )

    def _walk_webp(self) -> None:
        data = self.data
        (riff_size,) = struct.unpack("<I", data[4:8])
        end = min(len(data), 8 + riff_size)
        pos = 12
        while pos + 8 <= end:
            fourcc = data[pos : pos + 4].decode("latin-1")
            (size,) = struct.unpack("<I", data[pos + 4 : pos + 8])
            body = data[pos + 8 : pos + 8 + size]
            pos += 8 + size + (size % 2)
            self.structure.append(fourcc.strip())
            location = f"WebP {fourcc.strip()}"
            if fourcc in _WEBP_STRUCTURAL:
                continue
            if fourcc == "ICCP":
                self._inspect_icc(body, location)
            elif fourcc == "EXIF":
                self._inspect_exif(body, location)
            elif fourcc == "XMP ":
                self._inspect_xmp(body, location)
            elif fourcc == "C2PA":
                self._inspect_c2pa(body, location)
            else:
                self._add("unknown_block", MEDIUM, f"Unknown WebP chunk “{fourcc}”", f"{size:,} bytes", location)
                self._inspect_text(_printable(body[:262144]), location)
        self._trailing(data[8 + riff_size :], "after WebP data")

    def _walk_bmff(self) -> None:
        data = self.data
        pos = 0
        end = len(data)
        while pos + 8 <= end:
            size, kind_raw = struct.unpack(">I4s", data[pos : pos + 8])
            header = 8
            if size == 1:
                (size,) = struct.unpack(">Q", data[pos + 8 : pos + 16])
                header = 16
            elif size == 0:
                size = end - pos
            if size < header:
                raise ValueError("box with an invalid size")
            kind = kind_raw.decode("latin-1")
            body = data[pos + header : pos + size]
            pos += size
            self.structure.append(kind)
            if kind in _BMFF_STRUCTURAL:
                continue
            if kind == "uuid" and body[:16] == _C2PA_BMFF_UUID:
                self._inspect_c2pa(body, "HEIF/AVIF uuid box")
            elif kind == "jumb":
                self._inspect_c2pa(body, "HEIF/AVIF jumb box")
            else:
                self._add("unknown_block", MEDIUM, f"Extra “{kind}” box", f"{len(body):,} bytes", "HEIF/AVIF")
                self._inspect_text(_printable(body[:262144]), f"HEIF/AVIF {kind}")

    def _trailing(self, tail: bytes, where: str) -> None:
        if not tail:
            return
        if b"\xff\xd8\xff" in tail:
            count = tail.count(b"\xff\xd8\xff")
            self._add(
                "extra_images",
                MEDIUM,
                "Extra embedded images",
                f"{count} hidden image{'s' if count != 1 else ''} appended {where}",
                "Trailing data",
            )
        else:
            self._add(
                "trailing_data",
                MEDIUM,
                "Hidden data after the image",
                f"{len(tail):,} bytes {where}",
                "Trailing data",
            )
        self._inspect_text(_printable(tail[:262144]), "Trailing data")

    # ---- decoder-level + raw sweeps -----------------------------------------------------

    def _inspect_decoded(self, *, trust_walker: bool) -> dict | None:
        try:
            img = Image.open(BytesIO(self.data))
        except Exception:
            return None
        with img:
            info_dict = {
                "format": img.format,
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "frames": int(getattr(img, "n_frames", 1) or 1),
            }
            if not trust_walker:
                self._inspect_pillow_info(img)
            if "A" in img.getbands() and img.width * img.height <= MAX_PIXEL_CHECK:
                try:
                    img.load()
                    if _has_stealth_alpha(img.getchannel("A")):
                        self._add(
                            "stealth_alpha",
                            HIGH,
                            "Prompt hidden in transparency pixels",
                            "NovelAI-style payload in the alpha channel",
                            "Pixels",
                        )
                except Exception:
                    pass
        return info_dict

    def _inspect_pillow_info(self, img: Image.Image) -> None:
        fmt = img.format or self.container.upper()
        info = img.info
        exif = info.get("exif")
        if isinstance(exif, (bytes, bytearray)) and exif:
            self._inspect_exif(bytes(exif), f"{fmt} EXIF")
        xmp = info.get("xmp") or info.get("XML:com.adobe.xmp")
        if isinstance(xmp, str):
            xmp = xmp.encode("utf-8")
        if isinstance(xmp, (bytes, bytearray)) and xmp:
            self._inspect_xmp(bytes(xmp), f"{fmt} XMP")
        icc = info.get("icc_profile")
        if isinstance(icc, (bytes, bytearray)) and icc:
            self._inspect_icc(bytes(icc), f"{fmt} ICC")
        comment = info.get("comment")
        if comment:
            text = _decode(comment) if isinstance(comment, (bytes, bytearray)) else str(comment)
            self._add("comment", MEDIUM, "Hidden comment", f"“{_excerpt(text)}”", f"{fmt} comment")
            self._inspect_text(text, f"{fmt} comment")
        photoshop = info.get("photoshop")
        if isinstance(photoshop, dict) and photoshop:
            self._add("photoshop_irb", MEDIUM, "Photoshop / IPTC block", f"{len(photoshop)} resources", fmt)
        if fmt == "TIFF":
            tags = getattr(img, "tag_v2", {}) or {}
            if 33723 in tags:
                raw = tags[33723]
                blob = raw if isinstance(raw, bytes) else bytes(raw) if isinstance(raw, (list, tuple)) else b""
                self._inspect_iim(blob, "TIFF IPTC")
            if 52545 in tags:
                self._add("c2pa_manifest", CRITICAL, "Content Credentials (C2PA)", "TIFF C2PA tag", "TIFF", True)
        frames = int(getattr(img, "n_frames", 1) or 1)
        if frames > 1 and fmt in ("HEIF", "AVIF", "TIFF", "MPO"):
            self._add(
                "extra_images",
                MEDIUM,
                "Extra embedded images",
                f"{frames - 1} additional image{'s' if frames > 2 else ''} in the file",
                fmt,
            )

    def _raw_sweep(self) -> None:
        data = self.data
        at = _first(data, _RAW_C2PA)
        if at != -1 and not self._has("c2pa_manifest"):
            start = max(0, at - 64)
            self._inspect_c2pa(data[start : at + 65536], "Raw bytes")
        at = _first(data, _RAW_XMP)
        if at != -1 and not self._has("xmp"):
            self._inspect_xmp(data[at : at + 262144], "Raw bytes")
        at = _first(data, _RAW_EXIF)
        if at != -1 and not self._has("exif"):
            self._inspect_exif(data[at : at + 262144], "Raw bytes")
        if _first(data, _RAW_IRB) != -1 and not (self._has("photoshop_irb") or self._has("iptc_iim")):
            self._add("photoshop_irb", MEDIUM, "Photoshop / IPTC block", "Found in raw bytes", "Raw bytes")

        low = data.lower()
        at = _first(low, _RAW_DST)
        if at != -1 and not self._has("iptc_digital_source_type"):
            self._inspect_dst(data[max(0, at - 200) : at + 200].decode("latin-1"), "Raw bytes")
        for term in _RAW_TOOLS:
            at = low.find(term)
            if at == -1:
                continue
            text = data[at : at + len(term)].decode("utf-8", "replace")
            for name in _tool_names(text):
                if not self._has("ai_tool_reference", f"Names {name}"):
                    self._add("ai_tool_reference", HIGH, f"Names {name}", f"“{text}” in file bytes", "Raw bytes")
        if b"negative prompt" in low and not self._has("generation_parameters"):
            self._add(
                "generation_parameters",
                HIGH,
                "AI prompt or generation settings",
                "“Negative prompt” in file bytes",
                "Raw bytes",
            )
        if b"stealth_png" in low and not self._has("stealth_alpha"):
            self._add("stealth_alpha", HIGH, "Prompt hidden in transparency pixels", "stealth marker", "Raw bytes")

    def _inspect_filename(self) -> None:
        name = PureWindowsPath(self.filename).name if self.filename else ""
        if name and filename_has_ai_hint(name):
            self._add(
                "filename_hint",
                HIGH,
                "File name looks AI-generated",
                f"“{name[:80]}”",
                "File name",
            )


def _first(data: bytes, markers: tuple[bytes, ...]) -> int:
    hits = [i for i in (data.find(m) for m in markers) if i != -1]
    return min(hits) if hits else -1


def _c2pa_generator(blob: bytes) -> str | None:
    """Read the claim generator name from the manifest's CBOR claim."""
    for key in (b"claim_generator_info", b"claim_generator"):
        at = blob.find(key)
        while at != -1:
            pos = at + len(key)
            if key == b"claim_generator_info":
                name_at = blob.find(b"name", pos, pos + 16)
                pos = name_at + 4 if name_at != -1 else len(blob)
            text = _cbor_text(blob, pos)
            if text:
                return text
            at = blob.find(key, at + 1)
    return None


def _cbor_text(blob: bytes, pos: int) -> str | None:
    if pos >= len(blob):
        return None
    head = blob[pos]
    if 0x60 <= head <= 0x77:
        size, pos = head - 0x60, pos + 1
    elif head == 0x78 and pos + 1 < len(blob):
        size, pos = blob[pos + 1], pos + 2
    elif head == 0x79 and pos + 2 < len(blob):
        size, pos = int.from_bytes(blob[pos + 1 : pos + 3], "big"), pos + 3
    else:
        return None
    try:
        text = blob[pos : pos + size].decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return text[:80] or None


def _skip_entropy(data: bytes, pos: int) -> int:
    """Return the offset of the next real marker after entropy-coded scan data."""
    end = len(data)
    while True:
        pos = data.find(b"\xff", pos)
        if pos == -1 or pos + 1 >= end:
            return end
        nxt = data[pos + 1]
        if nxt == 0x00 or 0xD0 <= nxt <= 0xD7 or nxt == 0xFF:
            pos += 1 if nxt == 0xFF else 2
            continue
        return pos


def _xmp_value(text: str, key: str) -> str | None:
    attr = re.search(rf"{re.escape(key)}\s*=\s*[\"']([^\"']*)[\"']", text)
    if attr and attr.group(1).strip():
        return attr.group(1).strip()
    elem = re.search(rf"<{re.escape(key)}(?:\s[^>]*)?>(.*?)</{re.escape(key)}>", text, re.S)
    if elem:
        inner = re.sub(r"<[^>]+>", " ", elem.group(1))
        inner = " ".join(inner.split())
        if inner:
            return inner
        resource = re.search(r"rdf:resource\s*=\s*[\"']([^\"']+)", elem.group(0))
        if resource:
            return resource.group(1)
    resource = re.search(rf"<{re.escape(key)}[^>]*rdf:resource\s*=\s*[\"']([^\"']+)", text)
    return resource.group(1) if resource else None


def _exif_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        raw = value
        if raw[:8] in (b"ASCII\x00\x00\x00", b"UNICODE\x00", b"JIS\x00\x00\x00\x00\x00", b"\x00" * 8):
            raw = raw[8:]
        text = _decode(raw)
    elif isinstance(value, (tuple, list)):
        try:
            text = _decode(bytes(value))
        except (TypeError, ValueError):
            text = " ".join(str(v) for v in value)
    else:
        text = str(value)
    text = text.strip().strip("\x00")
    return text or None


def _imagemagick_profile(value: str) -> bytes | None:
    lines = value.strip().splitlines()
    if len(lines) < 3:
        return None
    try:
        return bytes.fromhex("".join(line.strip() for line in lines[2:]))
    except ValueError:
        return None


def _has_stealth_alpha(alpha: Image.Image) -> bool:
    width, height = alpha.size
    if width * height < 120:
        return False
    bits = []
    for i in range(120):
        x, y = divmod(i, height)
        bits.append(alpha.getpixel((x, y)) & 1)
    magic = bytes(int("".join(map(str, bits[j : j + 8])), 2) for j in range(0, 120, 8))
    return magic in (b"stealth_pnginfo", b"stealth_pngcomp")
