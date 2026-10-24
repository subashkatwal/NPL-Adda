"""
Server-side meme imaging with Pillow.

* ``store_upload`` validates a fan's image (type, bytes, pixel count), strips metadata and
  re-encodes it, so only clean JPEG data ever reaches storage.
* ``render_meme`` draws the final 1080x1080 meme: a template's drawn background, a template
  image or the fan's upload, then the top/bottom captions with auto-fitted, outlined text.
  Nepali (Devanagari) text uses Noto Sans Devanagari with complex-script shaping (raqm).
"""
import hashlib
import io
import os
import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError, features

SIZE = 1080
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_STORED_SIDE = 2048
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

FONT_DIRS = ["/usr/share/fonts/truetype/noto", "/usr/share/fonts/opentype/noto", "/usr/share/fonts/truetype/dejavu"]
LATIN_FONTS = ["NotoSans-CondensedBlack.ttf", "NotoSans-CondensedExtraBold.ttf", "NotoSans-Black.ttf",
               "NotoSans-ExtraBold.ttf", "NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"]
DEVANAGARI_FONTS = ["NotoSansDevanagari-Black.ttf", "NotoSansDevanagari-ExtraBold.ttf", "NotoSansDevanagari-Bold.ttf"]
SMALL_FONTS = ["NotoSans-SemiBold.ttf", "NotoSans-Medium.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf"]


class ImageRejected(Exception):
    """The upload is not an acceptable image; ``message`` is safe to show the fan."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------- uploads

def store_upload(file_obj):
    """Validate and re-encode an uploaded image. Returns (ContentFile, width, height, sha256)."""
    max_bytes = settings.MEME_UPLOAD_MAX_BYTES
    if getattr(file_obj, "size", 0) > max_bytes:
        raise ImageRejected(f"Images must be {max_bytes // (1024 * 1024)} MB or smaller.")
    data = file_obj.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ImageRejected(f"Images must be {max_bytes // (1024 * 1024)} MB or smaller.")
    Image.MAX_IMAGE_PIXELS = settings.MEME_UPLOAD_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ImageRejected("Use a JPEG, PNG or WebP image.")
            if probe.width * probe.height > settings.MEME_UPLOAD_MAX_PIXELS:
                raise ImageRejected("That image is too large in pixels.")
            probe.verify()  # structural check; the image must be reopened after this
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)  # respect orientation, then drop all metadata
            img = _flatten(img)
            img.thumbnail((MAX_STORED_SIDE, MAX_STORED_SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, "JPEG", quality=88, optimize=True)
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise ImageRejected("That file isn't a readable image.")
    payload = out.getvalue()
    return ContentFile(payload, name=f"{uuid.uuid4().hex}.jpg"), img.width, img.height, hashlib.sha256(payload).hexdigest()


def _flatten(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, "#0B1020")
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    return img.convert("RGB")


# ---------------------------------------------------------------- rendering

@dataclass
class MemeSpec:
    top_text: str = ""
    bottom_text: str = ""
    layout: dict = field(default_factory=dict)  # template layout_config
    background_path: object = None  # uploaded image or template image (filesystem path or binary file object)
    extra_paths: list = field(default_factory=list)  # more photos for a collage (style["collage"])
    team: dict | None = None  # {"short_name", "primary_color", "secondary_color"}
    style: dict = field(default_factory=dict)  # text_style


# Caption fonts fans can pick: (Latin font file, Devanagari font file). All ship with fonts-noto-core.
FONT_FAMILIES = {
    "bold": ("NotoSans-Bold.ttf", "NotoSansDevanagari-Bold.ttf"),
    "display": ("NotoSansDisplay-Bold.ttf", "NotoSansDevanagari-Bold.ttf"),
    "italic": ("NotoSans-BoldItalic.ttf", "NotoSansDevanagari-Bold.ttf"),
    "serif": ("NotoSerif-Bold.ttf", "NotoSerifDevanagari-Bold.ttf"),
    "mono": ("NotoSansMono-Bold.ttf", "NotoSansDevanagari-Bold.ttf"),
    "clean": ("NotoSans-Regular.ttf", "NotoSansDevanagari-Regular.ttf"),
}
COLLAGES = {"single": 1, "side": 2, "stack": 2, "grid": 4}  # layout -> photos it shows
TEXT_STYLE_DEFAULTS = {
    "top_y": 0.04, "bottom_y": 0.78, "size": 1.0, "top_size": 1.0, "bottom_size": 1.0, "color": "#F5F7FA",
    "align": "center", "font": "bold", "caps": True, "outline": True, "band": False, "collage": "single",
}


def clean_text_style(value):
    """Validate the caption style JSON; returns a normalised dict or raises ValueError."""
    if value in (None, ""):
        value = {}
    if not isinstance(value, dict):
        raise ValueError("Must be an object.")
    out = dict(TEXT_STYLE_DEFAULTS)
    for key in ("caps", "outline", "band"):
        if key in value:
            if not isinstance(value[key], bool):
                raise ValueError(f"{key} must be true or false.")
            out[key] = value[key]
    for key, allowed in (("font", FONT_FAMILIES), ("collage", COLLAGES)):
        if key in value:
            if value[key] not in allowed:
                raise ValueError(f"{key} must be one of {sorted(allowed)}.")
            out[key] = value[key]
    for key, low, high in (("top_y", 0.0, 0.5), ("bottom_y", 0.5, 0.95), ("size", 0.5, 2.0),
                           ("top_size", 0.5, 2.0), ("bottom_size", 0.5, 2.0)):
        if key in value:
            try:
                number = float(value[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number.")
            if not low <= number <= high:
                raise ValueError(f"{key} must be between {low} and {high}.")
            out[key] = round(number, 3)
    if "color" in value:
        if not isinstance(value["color"], str) or not HEX.match(value["color"]):
            raise ValueError("color must be #RRGGBB.")
        out["color"] = value["color"].upper()
    if "align" in value:
        if value["align"] not in ("left", "center", "right"):
            raise ValueError("align must be left, center or right.")
        out["align"] = value["align"]
    unknown = set(value) - set(out)
    if unknown:
        raise ValueError(f"Unknown keys: {sorted(unknown)}.")
    return out


@lru_cache(maxsize=1)
def font_paths():
    def find(names):
        for name in names:
            for folder in FONT_DIRS:
                path = os.path.join(folder, name)
                if os.path.exists(path):
                    return path
        return None
    return {"latin": find(LATIN_FONTS), "devanagari": find(DEVANAGARI_FONTS), "small": find(SMALL_FONTS)}


def rendering_status():
    """What the renderer can do on this server (shown in health/admin, used by tests)."""
    paths = font_paths()
    return {"latin_font": bool(paths["latin"]), "devanagari_font": bool(paths["devanagari"]),
            "complex_script_shaping": features.check("raqm")}


def _find_font(name):
    for folder in FONT_DIRS:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    return None


@lru_cache(maxsize=128)
def _font(kind, px, family="bold"):
    """kind: latin | devanagari | small. A missing family file falls back to the default fonts."""
    path = None
    if kind in ("latin", "devanagari") and family in FONT_FAMILIES:
        path = _find_font(FONT_FAMILIES[family][0 if kind == "latin" else 1])
    path = path or font_paths()[kind] or font_paths()["latin"]
    if not path:
        return ImageFont.load_default(size=px)
    layout = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, px, layout_engine=layout)


DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ꣠-ꣿ᳐-᳿‌‍]+")


class MixedFont:
    """
    Draws text that mixes Nepali and English. The Devanagari font has no Latin letters (they
    come out as empty boxes), so each run is measured and drawn in the font for its script,
    on a shared baseline. Quacks like ImageFont for ``getlength`` so wrapping is unchanged.
    """

    def __init__(self, px, family="bold"):
        self.px = px
        self.fonts = {"dev": _font("devanagari", px, family), "lat": _font("latin", px, family)}

    def runs(self, text):
        pos = 0
        for m in DEVANAGARI_RUN.finditer(text):
            if m.start() > pos:
                yield "lat", text[pos:m.start()]
            yield "dev", m.group()
            pos = m.end()
        if pos < len(text):
            yield "lat", text[pos:]

    def getlength(self, text):
        return sum(self.fonts[kind].getlength(part) for kind, part in self.runs(text))

    def draw(self, draw, xy, text, *, align, **kwargs):
        x, y = xy
        width = self.getlength(text)
        x -= {"left": 0, "center": width / 2, "right": width}[align]
        baseline = y + self.fonts["lat"].getmetrics()[0]  # ascent of the Latin font
        for kind, part in self.runs(text):
            draw.text((x, baseline), part, font=self.fonts[kind], anchor="ls", **kwargs)
            x += self.fonts[kind].getlength(part)


def _font_for(text, px, family="bold"):
    return MixedFont(px, family) if DEVANAGARI.search(text) else _font("latin", px, family)


def wrap(text, font, max_width):
    """Greedy word wrap; words longer than a line are broken by character."""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if font.getlength(candidate) <= max_width:
            line = candidate
            continue
        if line:
            lines.append(line)
        if font.getlength(word) <= max_width:
            line = word
            continue
        chunk = ""
        for ch in word:
            if font.getlength(chunk + ch) > max_width and chunk:
                lines.append(chunk)
                chunk = ch
            else:
                chunk += ch
        line = chunk
    if line:
        lines.append(line)
    return lines


def fit(text, max_width, max_height, start_px, family="bold"):
    """Largest font size (down to 22px) where the text fits in at most 4 lines."""
    for px in range(int(start_px), 21, -4):
        font = _font_for(text, px, family)
        lines = wrap(text, font, max_width)
        if len(lines) <= 4 and len(lines) * px * 1.12 <= max_height:
            return font, lines, px
    font = _font_for(text, 22, family)
    return font, wrap(text, font, max_width)[:5], 22


def draw_caption(draw, text, *, top, height, color, align, size_factor, anchor_bottom=False,
                 family="bold", caps=True, outline=True, band=False):
    text = text.strip()
    if not text:
        return
    if caps and not DEVANAGARI.search(text):  # Devanagari has no capitals
        text = text.upper()
    pad = SIZE * 0.05
    font, lines, px = fit(text, SIZE - pad * 2, height, SIZE * 0.095 * size_factor, family)
    line_h = px * 1.12
    block = len(lines) * line_h
    y = top + (height - block if anchor_bottom else 0)
    if band:  # dark strip behind the text, for busy photos
        draw.rectangle((0, y - px * 0.25, SIZE, y + block + px * 0.15), fill=(6, 9, 20, 140))
    x = {"left": pad, "center": SIZE / 2, "right": SIZE - pad}[align]
    anchor = {"left": "la", "center": "ma", "right": "ra"}[align]
    stroke = {"fill": color, "stroke_width": max(3, px // 12) if outline else 0, "stroke_fill": "#060914"}
    for line in lines:
        if isinstance(font, MixedFont):
            font.draw(draw, (x, y), line, align=align, **stroke)
        else:
            draw.text((x, y), line, font=font, anchor=anchor, **stroke)
        y += line_h


def _hex(value, fallback):
    return value if isinstance(value, str) and HEX.match(value) else fallback


def _cover(path, size=(SIZE, SIZE)):
    with Image.open(path) as img:
        img = _flatten(ImageOps.exif_transpose(img))
        return ImageOps.fit(img, size, Image.Resampling.LANCZOS)


def _collage(paths, kind):
    """Photos side by side, stacked or in a 2x2 grid, split by thin dark gutters."""
    cells = {
        "side": [(0, 0, 0.5, 1), (0.5, 0, 1, 1)],
        "stack": [(0, 0, 1, 0.5), (0, 0.5, 1, 1)],
        "grid": [(0, 0, 0.5, 0.5), (0.5, 0, 1, 0.5), (0, 0.5, 0.5, 1), (0.5, 0.5, 1, 1)],
    }[kind]
    canvas = Image.new("RGB", (SIZE, SIZE), "#0B1020")
    gutter = 4
    for i, (x0, y0, x1, y1) in enumerate(cells):
        path = paths[i % len(paths)]  # fewer photos than cells: repeat rather than leave holes
        box = (round(x0 * SIZE) + (gutter if x0 else 0), round(y0 * SIZE) + (gutter if y0 else 0),
               round(x1 * SIZE) - (gutter if x1 < 1 else 0), round(y1 * SIZE) - (gutter if y1 < 1 else 0))
        canvas.paste(_cover(path, (box[2] - box[0], box[3] - box[1])), box[:2])
    return canvas


def _glow(img, cx, cy, radius, color):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius * 0.45)))


def draw_background(layout, team):
    """Original drawn backgrounds (ports of the web templates); no third-party artwork."""
    primary = _hex(team.get("primary_color"), "#141C31")
    secondary = _hex(team.get("secondary_color"), "#C8FF4D")
    s = SIZE
    kind = layout.get("background", "scoreboard")
    img = Image.new("RGBA", (s, s), "#0B1020")
    d = ImageDraw.Draw(img)
    if kind == "split":
        d.rectangle((0, 0, s // 2, s), fill=primary)
        d.rectangle((s // 2 - 3, 0, s // 2 + 3, s), fill=secondary)
        labels = layout.get("labels") or ["Before", "After"]
        small = _font("small", int(s * 0.045))
        for i, label in enumerate(labels[:2]):
            d.text((s * (0.25 + 0.5 * i), s * 0.06), str(label).upper(), font=small, fill="#F5F7FA", anchor="ma")
    elif kind == "floodlights":
        for y in range(s):  # night sky to pitch green
            t = y / s
            d.line((0, y, s, y), fill=(int(6 + 13 * t), int(9 + 39 * t), int(20 + 11 * t)))
        for fx, fy in ((0.15, 0.12), (0.85, 0.12), (0.38, 0.2), (0.62, 0.2)):
            _glow(img, s * fx, s * fy, s * 0.17, (255, 246, 216, 200))
        d = ImageDraw.Draw(img)
        d.ellipse((s * -0.25, s * 0.7, s * 1.25, s * 1.4), fill="#2F6B3C")
    elif kind == "rain":
        d.rectangle((0, 0, s, s), fill="#1A2236")
        for i in range(90):
            x, y = (i * 97) % s, (i * 53) % s
            d.line((x, y, x - 8, y + 26), fill="#4A5570", width=2)
        d.rectangle((s * 0.1, s * 0.62, s * 0.9, s * 0.66), fill="#9AA6C2")
    elif kind == "review":
        d.rectangle((s * 0.06, s * 0.36, s * 0.94, s * 0.86), outline=secondary, width=3)
        for i in range(1, 4):
            x = s * (0.06 + i * 0.22)
            d.line((x, s * 0.36, x, s * 0.86), fill="#3B4A2A", width=2)
    else:  # scoreboard
        d.rectangle((0, 0, s, s * 0.14), fill=primary)
        for r in range(3):
            d.rectangle((s * 0.06, s * (0.2 + r * 0.12), s * 0.94, s * (0.29 + r * 0.12)), fill="#141C31")
        d.text((s * 0.06, s * 0.07), team.get("short_name") or "NPL", font=_font("latin", int(s * 0.07)),
               fill=secondary, anchor="lm")
        for b in range(6):
            cx, cy, r = s * (0.62 + b * 0.055), s * 0.07, s * 0.018
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#FF7043" if b < 4 else None, outline="#FF7043", width=3)
    return img


def render_meme(spec: MemeSpec):
    """Return the finished meme as an RGB ``PIL.Image`` (SIZE x SIZE)."""
    team = spec.team or {}
    layout = spec.layout or {}
    style = clean_text_style(spec.style or {})
    photos = [p for p in [spec.background_path, *spec.extra_paths] if p]
    if style["collage"] != "single" and photos:
        img = _collage(photos, style["collage"]).convert("RGBA")
    elif photos:
        img = _cover(photos[0]).convert("RGBA")
    else:
        img = draw_background(layout, team)
    draw = ImageDraw.Draw(img, "RGBA")  # RGBA mode blends the translucent caption band
    if layout.get("stamp") and not photos:
        draw.text((SIZE / 2, SIZE * 0.61), str(layout["stamp"]), font=_font("latin", int(SIZE * 0.07)),
                  fill="#FF7043", anchor="mm")
    text = {"color": style["color"], "align": style["align"], "family": style["font"], "caps": style["caps"],
            "outline": style["outline"], "band": style["band"]}
    draw_caption(draw, spec.top_text, top=SIZE * style["top_y"], height=SIZE * 0.24 * max(1, style["top_size"]),
                 size_factor=style["size"] * style["top_size"], **text)
    bottom_top = SIZE * style["bottom_y"]
    draw_caption(draw, spec.bottom_text, top=bottom_top - SIZE * 0.06, height=SIZE * 0.96 - bottom_top + SIZE * 0.06,
                 size_factor=style["size"] * style["bottom_size"], anchor_bottom=True, **text)
    draw.text((SIZE - SIZE * 0.03, SIZE - SIZE * 0.02), "NPL ADDA · fan-made", font=_font("small", int(SIZE * 0.022)),
              fill=(245, 247, 250, 170), anchor="rd")
    return img.convert("RGB")


def to_jpeg(img, quality=90):
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue()
