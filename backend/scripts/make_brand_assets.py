"""Generate the dogppelganger brand assets — favicon, touch icon, og:image.

The mark is the badge already in the header (`src/components/AppShell.tsx`):
the 🐶 emoji on a coral circle with a thick ink ring. This script reproduces it
at the sizes a browser wants and writes them into `public/`, which Vite copies
to `dist/` and the Dockerfile copies into the nginx image.

**The outputs are committed, so you almost certainly do not need to run this.**
Re-run it only when the brand colors in `src/styles.css` change, or to produce a
size that does not exist yet.

    python backend/scripts/make_brand_assets.py

Needs a colour emoji font, which is where this gets platform-specific: Segoe UI
Emoji on Windows, Apple Color Emoji on macOS, Noto Color Emoji on Linux. The
first one found wins; if none is present the script says so and stops rather
than silently drawing a blank circle. That platform dependency is exactly why
the results are committed instead of generated during the Docker build.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
PUBLIC = REPO / "public"

DOG = "\N{DOG FACE}"  # 🐶 — the same glyph the header renders


# --- colours -----------------------------------------------------------------
# src/styles.css states the palette in oklch(), which Pillow cannot parse, so we
# convert here rather than hardcoding hex that would silently drift from the CSS.
# The maths is the standard Oklab -> linear sRGB -> gamma-encoded sRGB pipeline.


def oklch_to_rgb(lightness: float, chroma: float, hue_deg: float) -> tuple[int, int, int]:
    """Convert an oklch() triple, as written in styles.css, to 8-bit sRGB."""
    a = chroma * math.cos(math.radians(hue_deg))
    b = chroma * math.sin(math.radians(hue_deg))

    # Oklab -> LMS (cube roots), then cube to get linear LMS.
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3

    linear = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )

    def encode(channel: float) -> int:
        channel = min(max(channel, 0.0), 1.0)
        srgb = 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055
        return round(min(max(srgb, 0.0), 1.0) * 255)

    return tuple(encode(c) for c in linear)  # type: ignore[return-value]


CORAL = oklch_to_rgb(0.72, 0.19, 35)  # --primary  #ff6f4a
INK = oklch_to_rgb(0.18, 0.03, 40)  # --ink      #1d0d07
CREAM = oklch_to_rgb(0.985, 0.02, 85)  # --background #fff9eb
MUTED = oklch_to_rgb(0.45, 0.03, 55)  # --muted-foreground

# The header badge is `h-10 w-10` with `border-2`: a 2px ring on a 40px circle.
RING_RATIO = 2 / 40
# How much of the circle's diameter the dog fills. The header uses text-xl in a
# 40px circle (0.5), but an icon seen at 16px needs the glyph to work harder, so
# this is tuned up to just inside the circle's inscribed square.
DOG_RATIO = 0.60
# Everything is drawn at this multiple and then LANCZOS-downsampled, which is
# what keeps the ring smooth at 16px instead of aliasing into a dotted line.
SUPERSAMPLE = 4


# --- fonts -------------------------------------------------------------------

EMOJI_FONTS = [
    "C:/Windows/Fonts/seguiemj.ttf",  # Windows — colour, scalable (COLR/CPAL)
    "/System/Library/Fonts/Apple Color Emoji.ttc",  # macOS — bitmap, fixed sizes
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux — bitmap, 109px only
]
# Bitmap emoji fonts (Apple, Noto) only accept the sizes baked into their strike
# table; Pillow raises OSError for anything else. 109 is the size both ship.
BITMAP_STRIKE = 109


def emoji_font(size: int) -> tuple[ImageFont.FreeTypeFont, int]:
    """Return a colour emoji font, plus the size it actually opened at.

    The caller scales the result, so a bitmap font that refuses `size` and falls
    back to its single strike still produces the right picture.
    """
    available = [p for p in EMOJI_FONTS if Path(p).exists()]
    if not available:
        sys.exit(
            "No colour emoji font found. Looked for:\n  "
            + "\n  ".join(EMOJI_FONTS)
            + "\n\nInstall one (on Debian/Ubuntu: `apt install fonts-noto-color-emoji`)\n"
            "or add its path to EMOJI_FONTS. The committed assets in public/ mean\n"
            "you only need this to regenerate them."
        )

    path = available[0]
    try:
        return ImageFont.truetype(path, size), size
    except OSError:
        # A bitmap font rejecting the requested size — take the strike instead.
        return ImageFont.truetype(path, BITMAP_STRIKE), BITMAP_STRIKE


def brand_font(weight: str, size: int, *, serif: bool) -> ImageFont.FreeTypeFont:
    """Load the real UI typeface from node_modules, or fall back to a system one.

    Pillow's FreeType reads .woff directly, so the fonts the app actually ships
    (@fontsource/fraunces, @fontsource/nunito) can be used rather than an
    approximation — but only when `npm install` has been run.
    """
    family = "fraunces" if serif else "nunito"
    woff = REPO / "node_modules" / "@fontsource" / family / "files"
    woff = woff / f"{family}-latin-{weight}-normal.woff"
    if woff.exists():
        return ImageFont.truetype(str(woff), size)

    fallback = "C:/Windows/Fonts/georgiab.ttf" if serif else "C:/Windows/Fonts/segoeuib.ttf"
    if Path(fallback).exists():
        return ImageFont.truetype(fallback, size)
    return ImageFont.load_default(size)


# --- the badge ---------------------------------------------------------------


def dog_glyph(target: int) -> Image.Image:
    """The dog emoji, rendered in colour and cropped to its own ink.

    Cropping to the real bounding box and centring *that* is what stops the dog
    sitting visibly high in the circle — emoji glyph boxes carry uneven padding,
    so trusting the font's metrics leaves it off-centre.
    """
    font, opened_at = emoji_font(target)
    canvas = Image.new("RGBA", (opened_at * 2, opened_at * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text(
        (opened_at, opened_at), DOG, font=font, anchor="mm", embedded_color=True
    )

    box = canvas.getbbox()
    if box is None:
        sys.exit("The emoji font rendered nothing — it may lack U+1F436 (dog face).")
    glyph = canvas.crop(box)

    scale = target / max(glyph.size)
    return glyph.resize(
        (max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale))),
        Image.Resampling.LANCZOS,
    )


def badge(size: int) -> Image.Image:
    """The header badge — coral disc, ink ring, dog — as a transparent RGBA square."""
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    ring = max(1, round(big * RING_RATIO))
    # Pillow strokes centred on the path, so inset by half the ring to keep the
    # whole outline inside the square instead of clipping it at the edge.
    inset = ring / 2
    draw.ellipse(
        [inset, inset, big - 1 - inset, big - 1 - inset], fill=CORAL, outline=INK, width=ring
    )

    dog = dog_glyph(round(big * DOG_RATIO))
    image.alpha_composite(dog, ((big - dog.width) // 2, (big - dog.height) // 2))

    return image.resize((size, size), Image.Resampling.LANCZOS)


# --- outputs -----------------------------------------------------------------


def hex_of(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def write_favicon_svg(path: Path) -> None:
    """The vector favicon modern browsers prefer.

    The emoji is left as text so it renders with whatever colour emoji font the
    viewer's OS has — the same way the header badge does.
    """
    view = 64
    ring = view * RING_RATIO
    radius = view / 2 - ring / 2
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {view} {view}">
  <title>dogppelganger</title>
  <circle cx="{view / 2}" cy="{view / 2}" r="{radius:.1f}"
          fill="{hex_of(CORAL)}" stroke="{hex_of(INK)}" stroke-width="{ring:.1f}" />
  <text x="{view / 2}" y="{view / 2}" font-size="{view * DOG_RATIO:.0f}"
        text-anchor="middle" dominant-baseline="central"
        font-family="'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif"
  >{DOG}</text>
</svg>
""",
        encoding="utf-8",
    )


def write_favicon_ico(path: Path) -> None:
    """A multi-resolution .ico for browsers that ignore the SVG.

    Each size is drawn from scratch rather than letting the ICO encoder shrink
    one big image, so the ring is tuned at every resolution.
    """
    sizes = [16, 32, 48]
    frames = [badge(s) for s in sizes]
    frames[-1].save(
        path, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1]
    )


def write_apple_touch_icon(path: Path) -> None:
    """180x180, deliberately opaque: iOS discards alpha and composites on black."""
    size = 180
    canvas = Image.new("RGBA", (size, size), CREAM + (255,))
    mark = badge(round(size * 0.82))
    canvas.alpha_composite(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    canvas.convert("RGB").save(path, format="PNG")


def write_og_image(path: Path) -> None:
    """1200x630 link-preview card: the badge, the wordmark, the tagline."""
    width, height = 1200, 630
    canvas = Image.new("RGBA", (width, height), CREAM + (255,))
    draw = ImageDraw.Draw(canvas)

    # The app's signature thick ink frame.
    border = 10
    draw.rectangle([0, 0, width - 1, height - 1], outline=INK, width=border)

    wordmark = brand_font("900", 108, serif=True)
    tagline = brand_font("700", 44, serif=False)

    mark_size = 190
    gap = 36
    text = "dogppelganger"
    text_width = draw.textlength(text, font=wordmark)

    row_width = mark_size + gap + text_width
    row_left = (width - row_width) / 2
    row_middle = height / 2 - 40

    mark = badge(mark_size)
    canvas.alpha_composite(mark, (round(row_left), round(row_middle - mark_size / 2)))
    draw.text(
        (row_left + mark_size + gap, row_middle), text, font=wordmark, fill=INK, anchor="lm"
    )

    draw.text(
        (width / 2, row_middle + mark_size / 2 + 60),
        "find the dog you already are",
        font=tagline,
        fill=MUTED,
        anchor="mm",
    )

    canvas.convert("RGB").save(path, format="PNG")


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    outputs = [
        ("favicon.svg", write_favicon_svg),
        ("favicon.ico", write_favicon_ico),
        ("apple-touch-icon.png", write_apple_touch_icon),
        ("og-image.png", write_og_image),
    ]
    for name, writer in outputs:
        target = PUBLIC / name
        writer(target)
        print(f"wrote {target.relative_to(REPO)}  ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
