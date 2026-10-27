import base64
import struct
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from app.auth.dependencies import get_verified_user
from app.routes import md_cleaner as md_cleaner_route
from app.services.md_cleaner import CleanError, clean_image, scan_bytes
from app.services.md_cleaner import cleaner as cleaner_module

AI_DST = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
XMP = (
    '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
    'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:CreatorTool="Adobe Firefly" '
    f'Iptc4xmpExt:DigitalSourceType="{AI_DST}"/>'
    "</rdf:RDF></x:xmpmeta><?xpacket end=\"w\"?>"
).encode()

LEAK_MARKERS = (
    b"c2pa",
    b"jumb",
    b"Exif\x00\x00",
    b"xmpmeta",
    b"Photoshop 3.0",
    b"trainedAlgorithmicMedia",
    b"Midjourney",
    b"Firefly",
    b"Google AI",
    b"ChatGPT",
    b"Negative prompt",
    b"ICC_PROFILE",
)


def _photo(size=(64, 48), color=(180, 120, 60)) -> Image.Image:
    img = Image.new("RGB", size, color)
    for x in range(size[0]):
        img.putpixel((x, 0), (x * 3 % 256, 40, 200))
    return img


def _c2pa_box() -> bytes:
    content = (
        b"\xa2\x6fclaim_generator\x6bChatGPT/1.0"
        b"\x6cc2pa.actions\x81\xa1\x71digitalSourceType\x78\x46" + AI_DST.encode()
    )
    jumd = b"jumd" + b"c2pa\x00\x11\x00\x10\x80\x00\x00\xaa\x00\x38\x9b\x71" + b"\x03c2pa\x00"
    jumd = struct.pack(">I", len(jumd) + 4) + jumd
    cbor = struct.pack(">I", len(content) + 8) + b"cbor" + content
    body = jumd + cbor
    return struct.pack(">I", len(body) + 8) + b"jumb" + body


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def _iptc_irb(credit: bytes) -> bytes:
    iim = b"\x1c\x02\x6e" + struct.pack(">H", len(credit)) + credit
    return b"Photoshop 3.0\x00" + b"8BIM\x04\x04\x00\x00" + struct.pack(">I", len(iim)) + iim


def _exif(**tags) -> bytes:
    exif = Image.Exif()
    for tag, value in tags.items():
        exif[int(tag, 16)] = value
    return exif.tobytes()


def _ai_jpeg(orientation: int = 1) -> bytes:
    buf = BytesIO()
    exif = _exif(
        **{
            "0x0131": "Midjourney",
            "0x010e": "a red bag on marble --ar 4:5 --v 6 Job ID: 1234",
            "0x0112": orientation,
        }
    )
    _photo().save(buf, "JPEG", quality=92, exif=exif, comment=b"made in ChatGPT")
    raw = buf.getvalue()
    extra = (
        _segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP)
        + _segment(0xEB, b"JP\x00\x01\x00\x00\x00\x01" + _c2pa_box())
        + _segment(0xED, _iptc_irb(b"Made with Google AI"))
    )
    thumb = BytesIO()
    _photo((8, 8)).save(thumb, "JPEG")
    return raw[:2] + extra + raw[2:] + thumb.getvalue()


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    import zlib

    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def _ai_png(img: Image.Image | None = None) -> bytes:
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a cat\nNegative prompt: blurry\nSteps: 30, Sampler: Euler a, Seed: 42")
    info.add_itxt("XML:com.adobe.xmp", XMP.decode())
    info.add_text("Software", "ComfyUI")
    buf = BytesIO()
    (img or _photo()).save(buf, "PNG", pnginfo=info)
    raw = buf.getvalue()
    iend = raw.rindex(b"IEND") - 4
    return raw[:iend] + _png_chunk(b"caBX", _c2pa_box()) + raw[iend:] + b"trailing-garbage"


def _p3_profile() -> bytes:
    def s15(v: float) -> bytes:
        return struct.pack(">i", round(v * 65536))

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ \x00\x00\x00\x00" + s15(x) + s15(y) + s15(z)

    curv = b"curv\x00\x00\x00\x00" + struct.pack(">IH", 1, 0x0233) + b"\x00\x00"
    name = b"Display P3\x00"
    desc = b"desc\x00\x00\x00\x00" + struct.pack(">I", len(name)) + name + b"\x00" * 78
    tags = [
        (b"desc", desc),
        (b"wtpt", xyz(0.9642, 1.0, 0.8249)),
        (b"rXYZ", xyz(0.5151, 0.2412, -0.0011)),
        (b"gXYZ", xyz(0.2920, 0.6922, 0.0419)),
        (b"bXYZ", xyz(0.1571, 0.0666, 0.7841)),
        (b"rTRC", curv),
        (b"gTRC", curv),
        (b"bTRC", curv),
        (b"cprt", b"text\x00\x00\x00\x00No copyright\x00\x00\x00\x00"),
    ]
    offset = 128 + 4 + 12 * len(tags)
    table = struct.pack(">I", len(tags))
    blobs = b""
    for sig, blob in tags:
        blob += b"\x00" * (-len(blob) % 4)
        table += sig + struct.pack(">II", offset + len(blobs), len(blob))
        blobs += blob
    size = 128 + len(table) + len(blobs)
    header = (
        struct.pack(">I", size)
        + b"lcms"
        + struct.pack(">I", 0x02100000)
        + b"mntrRGB XYZ "
        + b"\x00" * 12
        + b"acspAPPL"
        + b"\x00" * 20
        + struct.pack(">I", 0)
        + s15(0.9642)
        + s15(1.0)
        + s15(0.8249)
        + b"\x00" * 48
    )
    assert len(header) == 128
    return header + table + blobs


def _codes(report) -> set[str]:
    return {f.code for f in report.findings}


def _assert_bare(result) -> None:
    after = result.after
    assert after.verdict == "clean", after.to_dict()["findings"]
    assert all(check["passed"] for check in after.checks())
    for marker in LEAK_MARKERS:
        assert marker.lower() not in result.data.lower(), marker


def test_scan_reads_every_meta_signal_in_an_ai_jpeg():
    report = scan_bytes(_ai_jpeg(), "ChatGPT Image Mar 3, 2026.jpg")
    by_code = {f.code: f for f in report.findings}

    assert report.verdict == "ai_labeled"
    assert by_code["c2pa_manifest"].meta_signal
    assert "AI-generated" in by_code["c2pa_manifest"].detail
    assert "signed by “ChatGPT/1.0”" in by_code["c2pa_manifest"].detail
    assert "Names AI tool" not in {f.label for f in report.findings}
    assert by_code["iptc_digital_source_type"].severity == "critical"
    assert {"exif", "xmp", "iptc_iim", "comment", "extra_images", "filename_hint"} <= set(by_code)
    tools = {f.label for f in report.findings if f.code == "ai_tool_reference"}
    assert {"Names Midjourney", "Names Adobe Firefly", "Names Google AI", "Names OpenAI"} <= tools
    assert any(f.code == "generation_parameters" for f in report.findings)


def test_clean_jpeg_leaves_only_bare_pixels_and_keeps_it_upright():
    result = clean_image(_ai_jpeg(orientation=6), "ChatGPT Image.jpg")

    _assert_bare(result)
    assert result.format == "jpeg"
    assert set(result.after.structure) <= {"SOI", "APP0 JFIF", "DQT", "SOF0", "DHT", "SOS", "EOI"}
    assert (result.width, result.height) == (48, 64)
    assert any("rotation" in note for note in result.notes)
    assert result.fidelity["psnr_db"] is None or result.fidelity["psnr_db"] >= 38
    assert not result.filename.lower().startswith("chatgpt")
    assert result.before.verdict == "ai_labeled"


def test_png_generation_params_and_cabx_are_removed_losslessly():
    source = _photo()
    data = _ai_png(source)
    report = scan_bytes(data, "render.png")
    assert {"generation_parameters", "c2pa_manifest", "xmp", "trailing_data"} <= _codes(report)

    result = clean_image(data, "render.png")
    _assert_bare(result)
    assert result.format == "png"
    assert result.after.structure[0] == "IHDR" and result.after.structure[-1] == "IEND"
    assert result.fidelity == {"lossless": True, "psnr_db": None, "label": "Pixel-perfect"}
    with Image.open(BytesIO(result.data)) as out:
        assert out.convert("RGB").tobytes() == source.tobytes()
    assert result.filename == "render.png"


def test_webp_with_exif_xmp_and_c2pa_becomes_clean_jpeg():
    buf = BytesIO()
    _photo().save(buf, "WEBP", quality=90, exif=_exif(**{"0x0131": "DALL·E 3"}), xmp=XMP)
    raw = buf.getvalue()
    box = _c2pa_box()
    chunk = b"C2PA" + struct.pack("<I", len(box)) + box + b"\x00" * (len(box) % 2)
    (riff,) = struct.unpack("<I", raw[4:8])
    data = raw[:4] + struct.pack("<I", riff + len(chunk)) + raw[8:] + chunk

    report = scan_bytes(data, "x.webp")
    assert {"c2pa_manifest", "exif", "xmp", "iptc_digital_source_type"} <= _codes(report)

    result = clean_image(data, "x.webp")
    _assert_bare(result)
    assert result.format == "jpeg"


def test_display_p3_colors_are_converted_before_the_profile_is_dropped():
    buf = BytesIO()
    Image.new("RGB", (32, 32), (200, 100, 50)).save(buf, "JPEG", quality=100, icc_profile=_p3_profile())

    result = clean_image(buf.getvalue(), "p3.jpg")

    _assert_bare(result)
    assert any("Display P3" in note for note in result.notes)
    with Image.open(BytesIO(result.data)) as out:
        red, green, _ = out.getpixel((16, 16))
    assert red > 210 and green < 100


def test_transparency_is_kept_but_fully_opaque_alpha_is_dropped():
    clear = Image.new("RGBA", (40, 40), (10, 200, 10, 255))
    clear.putpixel((0, 0), (0, 0, 0, 0))
    buf = BytesIO()
    clear.save(buf, "PNG")
    kept = clean_image(buf.getvalue(), "logo.png")
    assert kept.format == "png"
    with Image.open(BytesIO(kept.data)) as out:
        assert out.mode == "RGBA" and out.getpixel((0, 0))[3] == 0

    buf = BytesIO()
    Image.new("RGBA", (40, 40), (10, 200, 10, 255)).save(buf, "PNG")
    dropped = clean_image(buf.getvalue(), "solid.png")
    with Image.open(BytesIO(dropped.data)) as out:
        assert out.mode == "RGB"


def test_jpeg_output_puts_transparent_areas_on_white():
    img = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    buf = BytesIO()
    img.save(buf, "PNG")
    result = clean_image(buf.getvalue(), "t.png", "jpeg")
    with Image.open(BytesIO(result.data)) as out:
        assert min(out.getpixel((10, 10))) >= 250
    assert any("white" in note for note in result.notes)


def test_prompt_hidden_in_alpha_pixels_is_found_and_wiped():
    img = Image.new("RGBA", (30, 30), (90, 90, 90, 255))
    payload = b"stealth_pnginfo"
    bits = "".join(f"{byte:08b}" for byte in payload)
    for i, bit in enumerate(bits):
        x, y = divmod(i, 30)
        img.putpixel((x, y), (90, 90, 90, 254 + int(bit)))
    buf = BytesIO()
    img.save(buf, "PNG")

    assert "stealth_alpha" in _codes(scan_bytes(buf.getvalue(), "n.png"))
    result = clean_image(buf.getvalue(), "n.png")
    _assert_bare(result)
    with Image.open(BytesIO(result.data)) as out:
        assert out.mode == "RGB"


def test_unusual_modes_decode_to_rgb():
    gray16 = Image.new("I;16", (16, 16), 40000)
    buf = BytesIO()
    gray16.save(buf, "PNG")
    result = clean_image(buf.getvalue(), "g.png")
    with Image.open(BytesIO(result.data)) as out:
        assert out.mode == "RGB" and 150 <= out.getpixel((1, 1))[0] <= 160

    cmyk = Image.new("CMYK", (16, 16), (0, 255, 255, 0))
    buf = BytesIO()
    cmyk.save(buf, "JPEG")
    result = clean_image(buf.getvalue(), "c.jpg")
    _assert_bare(result)
    with Image.open(BytesIO(result.data)) as out:
        assert out.getpixel((8, 8))[0] > 200


def test_animated_gif_keeps_first_frame_and_drops_comment():
    frames = [Image.new("RGB", (10, 10), color) for color in ((255, 0, 0), (0, 0, 255))]
    buf = BytesIO()
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], comment=b"midjourney v6")
    report = scan_bytes(buf.getvalue(), "a.gif")
    assert "comment" in _codes(report)
    result = clean_image(buf.getvalue(), "a.gif")
    _assert_bare(result)
    assert any("first frame" in note for note in result.notes)


def test_heic_metadata_is_read_and_removed():
    pillow_heif = pytest.importorskip("pillow_heif")
    buf = BytesIO()
    try:
        _photo().save(buf, "HEIF", exif=_exif(**{"0x0131": "Gemini"}), xmp=XMP)
    except Exception:
        pytest.skip("HEIF encoder unavailable")
    assert pillow_heif
    report = scan_bytes(buf.getvalue(), "p.heic")
    assert {"exif", "xmp", "iptc_digital_source_type"} <= _codes(report)
    result = clean_image(buf.getvalue(), "p.heic")
    _assert_bare(result)
    assert result.format == "jpeg"


def test_filenames_that_look_generated_are_replaced():
    for name in (
        "DALL·E 2026-01-02 10.00.00 - bag.png",
        "Gemini_Generated_Image_abc123.png",
        "user_red_bag_1f0a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8.png",
    ):
        assert cleaner_module.clean_filename(name, "jpeg").startswith("image-")
    assert cleaner_module.clean_filename("summer-hero.webp", "jpeg") == "summer-hero.jpg"


def test_rejects_files_that_are_not_pictures_or_too_big(monkeypatch):
    with pytest.raises(CleanError):
        clean_image(b"not an image at all", "x.jpg")
    monkeypatch.setattr(cleaner_module, "MAX_PIXELS", 100)
    with pytest.raises(CleanError, match="megapixels"):
        clean_image(_ai_jpeg(), "x.jpg")


def test_fails_closed_when_anything_survives_encoding(monkeypatch):
    real_encode = cleaner_module._encode

    def leaky(img, fmt, quality):
        raw = real_encode(img, fmt, quality)
        return raw[:2] + _segment(0xFE, b"leftover") + raw[2:]

    monkeypatch.setattr(cleaner_module, "_encode", leaky)
    with pytest.raises(CleanError, match="final check"):
        clean_image(_ai_jpeg(), "x.jpg")


def test_binary_inside_a_manifest_does_not_spell_tool_names():
    noisy = _c2pa_box() + b"\xff\xd8\xffSd\x853)\x92\xbbgrok\xa0"
    buf = BytesIO()
    _photo().save(buf, "PNG")
    raw = buf.getvalue()
    iend = raw.rindex(b"IEND") - 4
    report = scan_bytes(raw[:iend] + _png_chunk(b"caBX", noisy) + raw[iend:], "x.png")
    tools = {f.label for f in report.findings if f.code == "ai_tool_reference"}
    assert "Names Stable Diffusion" not in tools
    assert "c2pa_manifest" in _codes(report)


def test_already_clean_picture_scans_clean():
    buf = BytesIO()
    _photo().save(buf, "PNG")
    assert scan_bytes(buf.getvalue(), "plain.png").verdict == "clean"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(md_cleaner_route.router, prefix="/api/v1/md-cleaner")
    app.dependency_overrides[get_verified_user] = lambda: type("U", (), {"id": "user-1"})()
    return TestClient(app)


def test_clean_endpoint_returns_verified_file(client):
    res = client.post(
        "/api/v1/md-cleaner/clean",
        files={"file": ("Firefly bag.jpg", _ai_jpeg(), "image/jpeg")},
        data={"output_format": "auto"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["after"]["verdict"] == "clean"
    assert body["meta_signals_removed"] >= 2
    assert body["filename"].startswith("image-")
    data = base64.b64decode(body["data_base64"])
    assert data[:3] == b"\xff\xd8\xff" and b"c2pa" not in data


def test_scan_and_error_endpoints(client):
    res = client.post("/api/v1/md-cleaner/scan", files={"file": ("a.jpg", _ai_jpeg(), "image/jpeg")})
    assert res.status_code == 200 and res.json()["verdict"] == "ai_labeled"

    bad = client.post("/api/v1/md-cleaner/clean", files={"file": ("a.jpg", b"nope", "image/jpeg")})
    assert bad.status_code == 422
