#!/usr/bin/env python3
"""Generate PNG icons for the Chrome extension.

Creates a clean, modern icon with the character 筆 (brush/stroke) on a
rounded-rectangle background with a subtle gradient feel, plus the five
stroke symbols along the bottom edge.

Outputs:
    chrome-extension/icon48.png   (48x48, toolbar)
    chrome-extension/icon128.png  (128x128, store listing)
    chrome-extension/icon16.png   (16x16, favicon)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "chrome-extension"

# Colors
BG_TOP = (30, 100, 200)       # deep blue
BG_BOTTOM = (50, 140, 240)    # lighter blue
ACCENT = (255, 200, 60)       # warm gold for the main character
WHITE = (255, 255, 255)
SHADOW = (20, 70, 160)        # darker blue for subtle shadow


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a CJK font at the given size."""
    candidates = [
        "msyh.ttc",        # Microsoft YaHei (Windows)
        "msjh.ttc",        # Microsoft JhengHei (Windows Traditional)
        "simsun.ttc",      # SimSun (Windows)
        "NotoSansCJK-Regular.ttc",  # Noto (Linux)
        "/System/Library/Fonts/PingFang.ttc",  # macOS
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int,
                  fill_top: tuple, fill_bottom: tuple, size: int) -> None:
    """Draw a rounded rectangle with a vertical gradient."""
    x0, y0, x1, y1 = xy
    # Draw gradient line by line
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        r = int(fill_top[0] + (fill_bottom[0] - fill_top[0]) * t)
        g = int(fill_top[1] + (fill_bottom[1] - fill_top[1]) * t)
        b = int(fill_top[2] + (fill_bottom[2] - fill_top[2]) * t)
        draw.line([(x0, y), (x1, y)], fill=(r, g, b))

    # Mask corners to make it rounded
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)
    return mask


def generate_icon(size: int) -> Image.Image:
    """Generate a single icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)
    radius = max(4, size // 6)

    # Draw gradient background onto a temp image
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)

    for y in range(margin, size - margin):
        t = (y - margin) / max(1, size - 2 * margin - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        bg_draw.line([(margin, y), (size - margin - 1, y)], fill=(r, g, b, 255))

    # Create rounded rectangle mask
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [margin, margin, size - margin - 1, size - margin - 1],
        radius=radius, fill=255
    )
    bg.putalpha(mask)
    img = Image.alpha_composite(img, bg)
    draw = ImageDraw.Draw(img)

    # Main character: 筆
    main_font_size = int(size * 0.55)
    main_font = _load_font(main_font_size)
    cx, cy = size // 2, int(size * 0.42)

    # Shadow
    draw.text((cx + 1, cy + 1), "筆", fill=(*SHADOW, 180), font=main_font, anchor="mm")
    # Main text
    draw.text((cx, cy), "筆", fill=(*ACCENT, 255), font=main_font, anchor="mm")

    # Bottom row: five stroke symbols 一丨丿丶乙
    if size >= 48:
        strokes = "一丨丿丶乙"
        small_font_size = max(8, int(size * 0.13))
        small_font = _load_font(small_font_size)
        bottom_y = int(size * 0.78)
        total_width = size - 2 * margin
        spacing = total_width / (len(strokes) + 1)

        for i, ch in enumerate(strokes):
            sx = margin + int(spacing * (i + 1))
            draw.text((sx, bottom_y), ch, fill=(*WHITE, 220), font=small_font, anchor="mm")

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for size in [16, 48, 128]:
        icon = generate_icon(size)
        path = OUT_DIR / f"icon{size}.png"
        icon.save(path)
        print(f"  Created {path.name} ({size}x{size}, {path.stat().st_size:,} bytes)")

    print("Done!")


if __name__ == "__main__":
    main()
