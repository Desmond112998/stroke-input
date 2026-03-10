#!/usr/bin/env python3
"""Generate Chrome Web Store screenshots for the Stroke Input extension.

Creates promotional screenshots (1280x800) that simulate the extension
in use, showing:
  1. Main input view — typing strokes with candidates visible
  2. Phrase suggestion view — after selecting a character
  3. Key mapping reference — showing all stroke keys

Outputs to chrome-extension/screenshots/
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "chrome-extension" / "screenshots"
W, H = 1280, 800

# ── Colors ──
BROWSER_BG = (245, 245, 245)
TAB_BAR = (222, 225, 230)
URL_BAR_BG = (255, 255, 255)
PAGE_BG = (255, 255, 255)
TEXT_DARK = (33, 33, 33)
TEXT_MID = (100, 100, 100)
TEXT_LIGHT = (170, 170, 170)
BLUE = (30, 100, 200)
BLUE_LIGHT = (230, 240, 255)
GOLD = (255, 185, 40)
OVERLAY_BG = (250, 250, 252)
OVERLAY_BORDER = (200, 205, 215)
CANDIDATE_HOVER = (235, 242, 255)
GREEN = (40, 167, 69)
INPUT_BORDER = (180, 185, 195)
STROKE_SYMBOL = (30, 100, 200)
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ["msyh.ttc", "msjh.ttc", "simsun.ttc"]:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _font_bold(size: int) -> ImageFont.FreeTypeFont:
    for name in ["msyhbd.ttc", "msjhbd.ttc"]:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return _font(size)


def _draw_browser_chrome(draw: ImageDraw.ImageDraw, url: str = "example.com") -> int:
    """Draw browser top bar (tabs + URL bar). Returns y where page content starts."""
    # Tab bar background
    draw.rectangle([0, 0, W, 72], fill=TAB_BAR)

    # Active tab
    draw.rounded_rectangle([12, 8, 220, 44], radius=8, fill=PAGE_BG)
    draw.text((28, 16), "Example Page", fill=TEXT_DARK, font=_font(14))

    # Window controls (dots)
    for i, color in enumerate([(255, 95, 87), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([W - 80 + i * 24, 16, W - 66 + i * 24, 30], fill=color)

    # URL bar
    draw.rounded_rectangle([12, 48, W - 12, 80], radius=6, fill=URL_BAR_BG,
                           outline=(210, 210, 210))
    draw.text((24, 55), f"🔒  {url}", fill=TEXT_MID, font=_font(14))

    return 84


def _draw_text_input(draw: ImageDraw.ImageDraw, x: int, y: int,
                     w: int, h: int, label: str, text: str,
                     cursor: bool = False) -> None:
    """Draw a form text input field."""
    draw.text((x, y - 28), label, fill=TEXT_DARK, font=_font(16))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6,
                           fill=WHITE, outline=INPUT_BORDER)
    draw.text((x + 12, y + (h - 20) // 2), text, fill=TEXT_DARK, font=_font(18))
    if cursor:
        tw = draw.textlength(text, font=_font(18))
        cx = x + 12 + int(tw) + 2
        draw.line([(cx, y + 8), (cx, y + h - 8)], fill=BLUE, width=2)


def _draw_overlay(draw: ImageDraw.ImageDraw, img: Image.Image,
                  x: int, y: int, w: int,
                  strokes: str, candidates: list[str],
                  status: str = "中", phrases: list[str] | None = None,
                  highlight_idx: int = -1) -> None:
    """Draw the stroke input overlay panel."""
    row_h = 40
    rows = 2 if phrases else 1
    total_h = 12 + 36 + rows * row_h + 28 + 12

    # Shadow
    draw.rounded_rectangle([x + 3, y + 3, x + w + 3, y + total_h + 3],
                           radius=10, fill=(0, 0, 0, 30))
    # Panel
    draw.rounded_rectangle([x, y, x + w, y + total_h],
                           radius=10, fill=OVERLAY_BG, outline=OVERLAY_BORDER)

    # Stroke display row
    sy = y + 12
    draw.text((x + 16, sy + 4), strokes, fill=STROKE_SYMBOL, font=_font(20))

    # Candidates row
    cy = sy + 36
    cx = x + 12
    for i, cand in enumerate(candidates):
        cw = 52
        if highlight_idx == i:
            draw.rounded_rectangle([cx, cy, cx + cw, cy + row_h - 4],
                                   radius=6, fill=CANDIDATE_HOVER)
        num_str = f"{i + 1}."
        draw.text((cx + 4, cy + 6), num_str, fill=TEXT_LIGHT, font=_font(13))
        draw.text((cx + 22, cy + 4), cand, fill=TEXT_DARK, font=_font(20))
        cx += cw

    # Phrases row (if any)
    if phrases:
        py = cy + row_h
        px = x + 12
        for i, ph in enumerate(phrases):
            pw = 24 + len(ph) * 22
            num_str = f"{i + 1}."
            draw.text((px + 4, py + 6), num_str, fill=TEXT_LIGHT, font=_font(13))
            draw.text((px + 22, py + 4), ph, fill=BLUE, font=_font(20))
            px += pw + 8

    # Status bar
    by = cy + rows * row_h + 4
    draw.text((x + 16, by), f"{status} | ` 開關 | Shift 中英切換",
              fill=TEXT_LIGHT, font=_font(12))


def _draw_key_badge(draw: ImageDraw.ImageDraw, x: int, y: int,
                    key: str, stroke: str, name: str, symbol: str,
                    size: int = 56) -> None:
    """Draw a single key mapping badge."""
    # Key cap
    draw.rounded_rectangle([x, y, x + size, y + size], radius=8,
                           fill=WHITE, outline=(190, 195, 205), width=2)
    draw.text((x + size // 2, y + size // 2), key,
              fill=TEXT_DARK, font=_font_bold(24), anchor="mm")
    # Arrow
    ax = x + size + 12
    draw.text((ax, y + size // 2 - 2), "→", fill=TEXT_LIGHT, font=_font(20), anchor="lm")
    # Stroke symbol
    sx = ax + 30
    draw.text((sx, y + 8), symbol, fill=STROKE_SYMBOL, font=_font(28))
    draw.text((sx, y + 38), name, fill=TEXT_MID, font=_font(13))


# ── Screenshot 1: Main Input ──

def screenshot_main_input() -> Image.Image:
    img = Image.new("RGBA", (W, H), BROWSER_BG)
    draw = ImageDraw.Draw(img)
    page_y = _draw_browser_chrome(draw, "translate.google.com")

    # Page background
    draw.rectangle([0, page_y, W, H], fill=PAGE_BG)

    # Page title
    draw.text((60, page_y + 30), "翻譯", fill=TEXT_DARK, font=_font_bold(28))
    draw.text((130, page_y + 36), "Translate", fill=TEXT_MID, font=_font(20))

    # Text area (simulating a translation input box)
    ta_x, ta_y, ta_w, ta_h = 60, page_y + 90, 560, 280
    draw.rounded_rectangle([ta_x, ta_y, ta_x + ta_w, ta_y + ta_h],
                           radius=10, fill=WHITE, outline=INPUT_BORDER)

    # Already typed text
    typed = "你好，我想學"
    draw.text((ta_x + 16, ta_y + 16), typed, fill=TEXT_DARK, font=_font(24))

    # Cursor
    tw = draw.textlength(typed, font=_font(24))
    cx = ta_x + 16 + int(tw) + 2
    draw.line([(cx, ta_y + 14), (cx, ta_y + 44)], fill=BLUE, width=2)

    # Overlay — showing strokes for 筆 with candidates
    _draw_overlay(draw, img,
                  x=ta_x + 20, y=ta_y + ta_h - 140, w=500,
                  strokes="丿 一 丶 一 丨 一 丨 一 丨 乙 一",
                  candidates=["筆", "畢", "鉍", "篳", "蓽", "嗶", "蹕", "壁", "碧"],
                  highlight_idx=0)

    # Right side: instruction callout
    bx, by = 680, page_y + 100
    draw.rounded_rectangle([bx, by, bx + 520, by + 260], radius=12,
                           fill=BLUE_LIGHT, outline=BLUE)
    draw.text((bx + 20, by + 16), "筆畫輸入法 Stroke Input", fill=BLUE,
              font=_font_bold(22))
    draw.text((bx + 20, by + 56), "按鍵輸入筆畫，即時匹配候選字",
              fill=TEXT_DARK, font=_font(17))

    # Mini key reference
    keys = [("J", "一", "橫"), ("K", "丨", "豎"), ("L", "丿", "撇"),
            ("U", "丶", "點"), ("I", "乙", "折"), ("O", "＊", "萬用")]
    for i, (k, sym, nm) in enumerate(keys):
        kx = bx + 20 + (i % 3) * 170
        ky = by + 100 + (i // 3) * 70
        # Key cap
        draw.rounded_rectangle([kx, ky, kx + 40, ky + 40], radius=6,
                               fill=WHITE, outline=(190, 195, 205), width=2)
        draw.text((kx + 20, ky + 20), k, fill=TEXT_DARK,
                  font=_font_bold(18), anchor="mm")
        draw.text((kx + 52, ky + 4), sym, fill=STROKE_SYMBOL, font=_font(22))
        draw.text((kx + 52, ky + 26), nm, fill=TEXT_MID, font=_font(12))

    return img


# ── Screenshot 2: Phrase Suggestions ──

def screenshot_phrases() -> Image.Image:
    img = Image.new("RGBA", (W, H), BROWSER_BG)
    draw = ImageDraw.Draw(img)
    page_y = _draw_browser_chrome(draw, "mail.google.com")

    draw.rectangle([0, page_y, W, H], fill=PAGE_BG)

    # Email compose area
    draw.text((60, page_y + 20), "撰寫新郵件", fill=TEXT_DARK, font=_font_bold(24))

    # To field
    _draw_text_input(draw, 60, page_y + 90, 700, 40, "收件人", "friend@example.com")

    # Subject field
    _draw_text_input(draw, 60, page_y + 170, 700, 40, "主旨", "今天開會")

    # Body area
    body_x, body_y, body_w, body_h = 60, page_y + 260, 700, 320
    draw.text((body_x, body_y - 28), "內容", fill=TEXT_DARK, font=_font(16))
    draw.rounded_rectangle([body_x, body_y, body_x + body_w, body_y + body_h],
                           radius=6, fill=WHITE, outline=INPUT_BORDER)

    body_text = "你好，今天嘅會議"
    draw.text((body_x + 12, body_y + 12), body_text, fill=TEXT_DARK, font=_font(20))

    # Cursor after 議
    tw = draw.textlength(body_text, font=_font(20))
    draw.line([(body_x + 12 + int(tw) + 2, body_y + 10),
               (body_x + 12 + int(tw) + 2, body_y + 36)], fill=BLUE, width=2)

    # Overlay showing phrase suggestions after selecting 會
    _draw_overlay(draw, img,
                  x=body_x + 20, y=body_y + 50, w=480,
                  strokes="",
                  candidates=[],
                  phrases=["議程", "議員", "議論", "議題", "議案", "議席"],
                  status="中")

    # Right side callout
    bx = 820
    draw.rounded_rectangle([bx, page_y + 100, bx + 400, page_y + 340],
                           radius=12, fill=BLUE_LIGHT, outline=BLUE)
    draw.text((bx + 20, page_y + 116), "詞組聯想", fill=BLUE, font=_font_bold(22))
    draw.text((bx + 20, page_y + 156),
              "選字後自動顯示常用詞組", fill=TEXT_DARK, font=_font(17))
    draw.text((bx + 20, page_y + 190),
              "按數字鍵即可快速輸入整個詞組", fill=TEXT_DARK, font=_font(17))
    draw.text((bx + 20, page_y + 240),
              "例：選「會」後顯示", fill=TEXT_MID, font=_font(15))
    draw.text((bx + 20, page_y + 270),
              "會議、會員、會計...", fill=STROKE_SYMBOL, font=_font(18))

    return img


# ── Screenshot 3: Key Mapping Reference ──

def screenshot_keys() -> Image.Image:
    img = Image.new("RGBA", (W, H), (240, 244, 250))
    draw = ImageDraw.Draw(img)

    # Title
    draw.text((W // 2, 50), "筆畫輸入法 Stroke Input",
              fill=BLUE, font=_font_bold(36), anchor="mt")
    draw.text((W // 2, 100), "按鍵對照 Key Mapping",
              fill=TEXT_MID, font=_font(22), anchor="mt")

    # Main key mappings — large cards
    keys_data = [
        ("J", "一", "橫 Horizontal", "héng"),
        ("K", "丨", "豎 Vertical", "shù"),
        ("L", "丿", "撇 Left-falling", "piě"),
        ("U", "丶", "點 Dot", "diǎn"),
        ("I", "乙", "折 Turning", "zhé"),
        ("O", "＊", "萬用 Wildcard", "—"),
    ]

    card_w, card_h = 340, 140
    cols = 3
    start_x = (W - cols * card_w - (cols - 1) * 30) // 2
    start_y = 160

    for i, (key, symbol, name, pinyin) in enumerate(keys_data):
        col = i % cols
        row = i // cols
        cx = start_x + col * (card_w + 30)
        cy = start_y + row * (card_h + 24)

        # Card
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h],
                               radius=12, fill=WHITE, outline=(220, 225, 235), width=2)

        # Key cap (left side)
        kx, ky = cx + 20, cy + (card_h - 64) // 2
        draw.rounded_rectangle([kx, ky, kx + 64, ky + 64], radius=10,
                               fill=(245, 247, 252), outline=(190, 195, 210), width=2)
        draw.text((kx + 32, ky + 32), key, fill=TEXT_DARK,
                  font=_font_bold(32), anchor="mm")

        # Arrow
        draw.text((cx + 104, cy + card_h // 2), "→",
                  fill=TEXT_LIGHT, font=_font(28), anchor="mm")

        # Stroke symbol (large)
        draw.text((cx + 150, cy + 20), symbol,
                  fill=STROKE_SYMBOL, font=_font(48))

        # Name + pinyin
        draw.text((cx + 210, cy + 30), name, fill=TEXT_DARK, font=_font(18))
        draw.text((cx + 210, cy + 58), pinyin, fill=TEXT_MID, font=_font(14))

        # Stroke code number
        code = str(i + 1) if i < 5 else "6"
        draw.text((cx + card_w - 20, cy + card_h - 16), code,
                  fill=TEXT_LIGHT, font=_font(13), anchor="rb")

    # Bottom section: control keys
    ctrl_y = start_y + 2 * (card_h + 24) + 40
    draw.text((W // 2, ctrl_y), "操作按鍵 Controls",
              fill=TEXT_MID, font=_font(20), anchor="mt")

    controls = [
        ("`", "開關 Toggle"),
        ("1-9", "選字 Select"),
        ("⌫", "刪除 Backspace"),
        ("Esc", "清除 Clear"),
        ("Space", "翻頁 Next Page"),
        ("Shift", "中/英 Toggle"),
    ]

    ctrl_start_x = (W - 6 * 180) // 2
    for i, (key, desc) in enumerate(controls):
        kx = ctrl_start_x + i * 180
        ky = ctrl_y + 40

        draw.rounded_rectangle([kx, ky, kx + 160, ky + 60], radius=8,
                               fill=WHITE, outline=(210, 215, 225))
        draw.text((kx + 80, ky + 14), key, fill=TEXT_DARK,
                  font=_font_bold(16), anchor="mt")
        draw.text((kx + 80, ky + 38), desc, fill=TEXT_MID,
                  font=_font(12), anchor="mt")

    # Example at bottom
    ex_y = ctrl_y + 140
    draw.rounded_rectangle([start_x, ex_y, W - start_x, ex_y + 80],
                           radius=12, fill=WHITE, outline=BLUE)
    draw.text((start_x + 20, ex_y + 10), "例 Example:",
              fill=BLUE, font=_font_bold(16))
    draw.text((start_x + 20, ex_y + 38),
              "輸入「大」→  J  L  U  (橫 撇 點)  →  按 1 選字",
              fill=TEXT_DARK, font=_font(18))

    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    shots = [
        ("screenshot-1-input.png", screenshot_main_input),
        ("screenshot-2-phrases.png", screenshot_phrases),
        ("screenshot-3-keys.png", screenshot_keys),
    ]

    for name, fn in shots:
        img = fn()
        path = OUT_DIR / name
        img.save(path)
        print(f"  Created {name} ({path.stat().st_size:,} bytes)")

    print(f"\nDone! Screenshots saved to {OUT_DIR}")


if __name__ == "__main__":
    main()
