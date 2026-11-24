"""
BNN Asia social photocard, 1024 × 1024 PNG, rendered on the server with Pillow.

Layout (fixed brand design):
  - the photo fills the whole card (cover-cropped, slightly toned down),
  - BNN ASIA logo top-left on a soft dark fade,
  - a black shade rising from the bottom carrying a red country label and the headline in white,
  - a footer line: "BNN ASIA | PROMOTING HUMAN RIGHTS, PRESS FREEDOM AND GOOD GOVERNANCE."

Fonts are bundled (SIL Open Font License): Anton (headline), Oswald (country label), Montserrat (logo, footer).
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

SIZE = 1024
MARGIN = 56
RED = (227, 30, 36)
WHITE = (255, 255, 255)
FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
TAGLINE = "PROMOTING HUMAN RIGHTS, PRESS FREEDOM AND GOOD GOVERNANCE."


@lru_cache(maxsize=64)
def _font(name: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / name), size)
    if weight:
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
    return f


def _cover(img: Image.Image, size: int, focus_y: float = 0.35) -> Image.Image:
    """Crop to a square that fills the card; vertical focus slightly above centre (faces, signs)."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    scale = size / min(w, h)
    img = img.resize((max(size, round(w * scale)), max(size, round(h * scale))), Image.LANCZOS)
    w, h = img.size
    left = (w - size) // 2
    top = int(max(0, min(h - size, (h - size) * focus_y)))
    return img.crop((left, top, left + size, top + size))


def _vertical_fade(size: int, stops: list[tuple[float, int]]) -> Image.Image:
    """Black layer whose alpha follows (position 0..1, alpha 0..255) stops from top to bottom."""
    col = Image.new("L", (1, size))
    px = col.load()
    for y in range(size):
        t = y / (size - 1)
        for (t0, a0), (t1, a1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                px[0, y] = round(a0 + (a1 - a0) * k)
                break
    alpha = col.resize((size, size))
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.putalpha(alpha)
    return layer


def _spaced(draw, xy, text, font, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _spaced_width(draw, text, font, spacing):
    return sum(draw.textlength(ch, font=font) for ch in text) + spacing * max(0, len(text) - 1)


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_title(draw, title, width, max_lines=4):
    for size in range(88, 46, -2):
        font = _font("Anton-Regular.ttf", size)
        lines = _wrap(draw, title, font, width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= width for l in lines):
            return font, lines
    font = _font("Anton-Regular.ttf", 46)
    lines = _wrap(draw, title, font, width)[:max_lines]
    lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return font, lines


def render(image_bytes: bytes | None, title: str, country: str = "", size: int = SIZE) -> bytes:
    title = " ".join((title or "").split()).upper()[:180]
    country = " ".join((country or "").split()).upper()[:40]

    if image_bytes:
        photo = _cover(Image.open(io.BytesIO(image_bytes)), size)
        photo = ImageEnhance.Color(photo).enhance(0.82)
        photo = ImageEnhance.Contrast(photo).enhance(1.08)
    else:
        photo = Image.new("RGB", (size, size), (24, 24, 28))
    card = photo.convert("RGBA")

    # Soft dark fade at the top for the logo, strong black shade from the bottom for the text.
    card = Image.alpha_composite(card, _vertical_fade(size, [(0, 150), (0.2, 40), (0.3, 0), (1, 0)]))
    card = Image.alpha_composite(card, _vertical_fade(size, [(0, 0), (0.38, 0), (0.62, 170), (0.78, 235), (1, 255)]))
    d = ImageDraw.Draw(card)

    # Logo, top-left.
    f_logo = _font("Montserrat.ttf", 60, "Black")
    x, y = MARGIN, 46
    d.text((x, y), "BNN", font=f_logo, fill=WHITE)
    d.text((x + d.textlength("BNN ", font=f_logo), y), "ASIA", font=f_logo, fill=RED)
    logo_w = d.textlength("BNN ASIA", font=f_logo)
    f_net = _font("Montserrat.ttf", 15, "Bold")
    tag_y = y + 70
    _spaced(d, (x + 2, tag_y), "BORDERLESS NEWS NETWORK", f_net, WHITE, 2.6)
    d.rectangle((x + 2, tag_y + 28, x + 2 + min(logo_w, 130), tag_y + 30), fill=RED)

    # Footer.
    foot_y = size - 74
    d.line((MARGIN, foot_y - 22, size - MARGIN, foot_y - 22), fill=(255, 255, 255, 90), width=1)
    f_fb = _font("Montserrat.ttf", 26, "ExtraBold")
    d.text((MARGIN, foot_y), "BNN", font=f_fb, fill=WHITE)
    d.text((MARGIN + d.textlength("BNN ", font=f_fb), foot_y), "ASIA", font=_font("Montserrat.ttf", 26, "Medium"), fill=WHITE)
    bx = MARGIN + d.textlength("BNN ASIA", font=f_fb) + 22
    d.line((bx, foot_y - 2, bx, foot_y + 34), fill=(255, 255, 255, 150), width=1)
    _spaced(d, (bx + 22, foot_y + 8), TAGLINE, _font("Montserrat.ttf", 12, "Medium"), (235, 235, 235), 1.6)

    # Headline block, laid out bottom-up above the footer.
    width = size - 2 * MARGIN
    f_title, lines = _fit_title(d, title, width)
    asc, desc = f_title.getmetrics()
    line_h = int((asc + desc) * 0.98)
    block_bottom = foot_y - 52
    title_top = block_bottom - line_h * len(lines)
    for i, line in enumerate(lines):
        d.text((MARGIN, title_top + i * line_h), line, font=f_title, fill=WHITE)

    if country:
        f_c = _font("Oswald.ttf", 30, "SemiBold")
        cy = title_top - 52
        d.rectangle((MARGIN, cy - 16, MARGIN + 54, cy - 11), fill=RED)
        _spaced(d, (MARGIN, cy), country, f_c, RED, 2.0)

    out = io.BytesIO()
    card.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
