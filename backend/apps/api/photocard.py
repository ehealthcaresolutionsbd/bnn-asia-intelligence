"""
BNN Asia social photocard, 1024 × 1024 PNG, rendered on the server with Pillow.

Layout (fixed brand design):
  - the photo fills the whole card (cover-cropped, slightly toned down),
  - cinematic grade (muted colour, cool shadows, vignette, light grain),
  - the BNN ASIA logo (white/red version) top-left,
  - a black shade over the lower part only, carrying a red country label (+ date) and a compact white headline.

Fonts are bundled (SIL Open Font License): Oswald.
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


def _grade(photo: Image.Image) -> Image.Image:
    """Cinematic grade: muted colour, firmer contrast, cool shadows / warm highlights, soft vignette."""
    photo = ImageEnhance.Color(photo).enhance(0.72)
    photo = ImageEnhance.Contrast(photo).enhance(1.12)
    r, g, b = photo.split()
    r = r.point(lambda v: min(255, int(v * 1.03 + (6 if v > 150 else 0))))
    b = b.point(lambda v: min(255, int(v * 0.97 + (8 if v < 90 else 0))))
    photo = Image.merge("RGB", (r, g, b))
    size = photo.size[0]
    vign = Image.radial_gradient("L").resize((size, size)).point(lambda v: int(v * 0.55))
    dark = Image.new("RGB", (size, size), (0, 0, 0))
    return Image.composite(dark, photo, vign)


def _grain(card: Image.Image, strength: int = 10) -> Image.Image:
    noise = Image.effect_noise(card.size, 40).point(lambda v: 128 + (v - 128) * strength // 40)
    noise = Image.merge("RGBA", (noise, noise, noise, Image.new("L", card.size, 18)))
    return Image.alpha_composite(card, noise)


@lru_cache(maxsize=1)
def _logo() -> Image.Image:
    return Image.open(FONT_DIR.parent / "logo-white.png").convert("RGBA")


def _fit_title(draw, title, width, max_lines=3):
    for size in range(54, 36, -2):
        font = _font("Oswald.ttf", size, "SemiBold")
        lines = _wrap(draw, title, font, width)
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= width for l in lines):
            return font, lines
    font = _font("Oswald.ttf", 36, "SemiBold")
    lines = _wrap(draw, title, font, width)[:max_lines]
    lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return font, lines


def render(image_bytes: bytes | None, title: str, country: str = "", date: str = "", size: int = SIZE) -> bytes:
    title = " ".join((title or "").split()).upper()[:160]
    country = " ".join((country or "").split()).upper()[:40]
    date = " ".join((date or "").split()).upper()[:24]

    if image_bytes:
        photo = _grade(_cover(Image.open(io.BytesIO(image_bytes)), size))
    else:
        photo = Image.new("RGB", (size, size), (20, 20, 24))
    card = photo.convert("RGBA")

    # Light fade behind the logo; the text shade only covers the lower part of the frame.
    card = Image.alpha_composite(card, _vertical_fade(size, [(0, 120), (0.16, 25), (0.24, 0), (1, 0)]))
    card = Image.alpha_composite(card, _vertical_fade(size, [(0, 0), (0.46, 0), (0.64, 175), (0.8, 235), (1, 252)]))
    card = _grain(card)
    d = ImageDraw.Draw(card)

    # Logo top-left.
    logo = _logo()
    lw = 270
    logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
    card.alpha_composite(logo, (MARGIN, 52))

    # Text block in the bottom area: red rule + country (+ date), then the headline, left-aligned.
    text_w = 780
    f_title, lines = _fit_title(d, title, text_w)
    asc, desc = f_title.getmetrics()
    line_h = int((asc + desc) * 1.0)
    bottom = size - 64
    title_top = bottom - line_h * len(lines)
    for i, line in enumerate(lines):
        d.text((MARGIN + 22, title_top + i * line_h), line, font=f_title, fill=WHITE)
    # Red accent bar alongside the headline.
    d.rectangle((MARGIN, title_top + 10, MARGIN + 5, bottom - 6), fill=RED)

    # Country tag: white letters on a red block; the date sits beside it in light grey.
    f_c = _font("Oswald.ttf", 21, "SemiBold")
    tag_y = title_top - 50
    x = MARGIN
    if country:
        tw = _spaced_width(d, country, f_c, 3.0)
        d.rectangle((MARGIN, tag_y, MARGIN + tw + 24, tag_y + 34), fill=RED)
        _spaced(d, (MARGIN + 12, tag_y + 1), country, f_c, WHITE, 3.0)
        x = MARGIN + tw + 24 + 16
    if date:
        _spaced(d, (x, tag_y + 1), date, f_c, (205, 205, 205), 3.0)

    out = io.BytesIO()
    card.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
