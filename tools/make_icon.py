"""Draws the app icon (assets/icon.ico): two overlapping headphones on a blue rounded square.

Run:  .venv\\Scripts\\python.exe tools\\make_icon.py   (needs Pillow; only used when building)
"""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def gradient(size, top, bottom):
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    return img


def headphones(d, cx, cy, r, w, color):
    # headband arc + two ear cups
    d.arc([cx - r, cy - r, cx + r, cy + r], start=180, end=360, fill=color, width=w)
    cup_w, cup_h = int(r * 0.42), int(r * 0.78)
    for side in (-1, 1):
        x = cx + side * (r - w // 2)
        d.rounded_rectangle([x - cup_w // 2, cy - cup_h * 0.15, x + cup_w // 2, cy + cup_h * 0.85],
                            radius=cup_w // 2.2, fill=color)


def main():
    base = gradient(S, (76, 194, 255), (40, 90, 220))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    headphones(d, int(S * 0.40), int(S * 0.50), int(S * 0.25), int(S * 0.055), (255, 255, 255, 120))
    headphones(d, int(S * 0.58), int(S * 0.46), int(S * 0.25), int(S * 0.055), (255, 255, 255, 255))
    icon = Image.alpha_composite(icon, layer)

    out = os.path.join(ROOT, "assets")
    os.makedirs(out, exist_ok=True)
    icon.save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                    (128, 128), (256, 256)])
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "icon.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
