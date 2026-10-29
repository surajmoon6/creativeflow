"""Server-side preview generation: downscale + tiled, project-specific watermark.

The preview is a separate asset. The client never receives the master/final bytes, only
this smaller JPEG with the watermark burned into the pixels.
"""
import io
import math

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_PIXELS = 60_000_000
MAX_PDF_PAGES = 30
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
PREVIEWABLE_EXTS = IMAGE_EXTS | {"pdf"}


class PreviewError(ValueError):
    pass


def _load_pages(data: bytes, ext: str, max_px: int) -> list[Image.Image]:
    if ext in IMAGE_EXTS:
        try:
            img = Image.open(io.BytesIO(data))
            img.verify()  # detects truncated/corrupt files
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)
        except Exception as e:  # noqa: BLE001 — any decode failure is a bad upload
            raise PreviewError("This file could not be read as an image.") from e
        if img.width * img.height > MAX_PIXELS:
            raise PreviewError("Image is too large.")
        return [img]
    if ext == "pdf":
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as e:  # noqa: BLE001
            raise PreviewError("This file could not be read as a PDF.") from e
        if doc.page_count == 0:
            raise PreviewError("The PDF has no pages.")
        pages = []
        for page in list(doc)[:MAX_PDF_PAGES]:
            longest = max(page.rect.width, page.rect.height) or 1
            zoom = min(4.0, max_px / longest)  # render straight at preview size
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return pages
    raise PreviewError("Previews support PNG, JPG, WEBP and PDF.")


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _downscale(img: Image.Image, max_px: int, scale: float) -> Image.Image:
    longest = max(img.size)
    target = min(max_px, int(longest * scale))
    if longest > target:
        ratio = target / longest
        img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))),
                         Image.LANCZOS)
    return img


def _watermark(img: Image.Image, lines: list[str], opacity: float) -> Image.Image:
    w, h = img.size
    alpha = int(255 * max(0.05, min(opacity, 0.9)))
    size = max(12, round(min(w, h) / 24))
    font = ImageFont.load_default(size=size)
    small = ImageFont.load_default(size=max(10, round(size * 0.7)))

    # Build one text tile.
    pad = size
    dummy = ImageDraw.Draw(Image.new("L", (1, 1)))
    fonts = [font] + [small] * (len(lines) - 1)
    boxes = [dummy.textbbox((0, 0), t, font=f, stroke_width=1) for t, f in zip(lines, fonts)]
    tile_w = max(b[2] - b[0] for b in boxes) + pad * 3
    line_h = [b[3] - b[1] + size // 3 for b in boxes]
    tile_h = sum(line_h) + pad * 2

    # Lay tiles on a canvas big enough to survive rotation, then rotate and crop.
    diag = int(math.hypot(w, h)) + tile_w
    layer = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    row = 0
    for y in range(0, diag, tile_h):
        offset = (tile_w // 2) if row % 2 else 0  # brick pattern
        for x in range(-offset, diag, tile_w):
            ty = y + pad
            for text, f, lh in zip(lines, fonts, line_h):
                d.text((x + pad, ty), text, font=f, fill=(255, 255, 255, alpha),
                       stroke_width=1, stroke_fill=(0, 0, 0, int(alpha * 0.55)))
                ty += lh
        row += 1
    layer = layer.rotate(28, resample=Image.BICUBIC)
    left, top = (diag - w) // 2, (diag - h) // 2
    layer = layer.crop((left, top, left + w, top + h))

    # Faint diagonal hairlines make clean inpainting a little harder.
    lines_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines_layer)
    step = max(18, size * 2)
    for x in range(-h, w, step):
        ld.line([(x, h), (x + h, 0)], fill=(255, 255, 255, alpha // 4), width=1)

    out = img.convert("RGBA")
    out = Image.alpha_composite(out, lines_layer)
    out = Image.alpha_composite(out, layer)
    return out.convert("RGB")


def generate_previews(data: bytes, ext: str, lines: list[str], *, max_px=1800, scale=0.9,
                      opacity=0.32, quality=86, watermark=True) -> list[tuple[bytes, int, int]]:
    """Returns [(jpeg_bytes, width, height)] — one entry per page. Always downscaled; the watermark is optional."""
    ext = ext.lower().lstrip(".")
    results = []
    for page in _load_pages(data, ext, max_px):
        img = _downscale(_flatten(page), max_px, scale)
        if watermark:
            img = _watermark(img, [l for l in lines if l], opacity)
        buf = io.BytesIO()
        # 4:4:4 keeps small text and thin edges crisp; a fresh image carries no EXIF/metadata.
        img.save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
        results.append((buf.getvalue(), img.width, img.height))
    return results


def image_size(data: bytes, ext: str):
    """Best-effort dimensions for display (finals/masters)."""
    ext = ext.lower()
    try:
        if ext in IMAGE_EXTS:
            with Image.open(io.BytesIO(data)) as im:
                return im.size
        if ext == "pdf":
            doc = pymupdf.open(stream=data, filetype="pdf")
            r = doc[0].rect
            return round(r.width), round(r.height)
    except Exception:  # noqa: BLE001
        pass
    return None, None
