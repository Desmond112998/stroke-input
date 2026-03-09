"""Generate simple PNG icons for the Chrome extension."""
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    # Fallback: create minimal valid PNGs without PIL
    import struct, zlib

    def create_png(size, path):
        """Create a minimal blue square PNG with no text."""
        # RGBA pixels: blue background
        raw = b""
        for y in range(size):
            raw += b"\x00"  # filter byte
            for x in range(size):
                raw += b"\x00\x78\xd7\xff"  # RGBA blue

        def chunk(ctype, data):
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
        idat = zlib.compress(raw)

        with open(path, "wb") as f:
            f.write(sig)
            f.write(chunk(b"IHDR", ihdr))
            f.write(chunk(b"IDAT", idat))
            f.write(chunk(b"IEND", b""))

    create_png(48, "chrome-extension/icon48.png")
    create_png(128, "chrome-extension/icon128.png")
    print("Created icons (plain blue squares)")
    exit()

for size, name in [(48, "icon48.png"), (128, "icon128.png")]:
    img = Image.new("RGBA", (size, size), (0, 120, 215, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("msyh.ttc", size // 2)
    except:
        font = ImageFont.load_default()
    draw.text((size//2, size//2), "筆", fill="white", font=font, anchor="mm")
    img.save(f"chrome-extension/{name}")
    print(f"Created {name}")
