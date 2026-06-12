#!/usr/bin/env python3
"""Generate a header banner for the NGS Daily Digest Slack message."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"

W, H = 1600, 480
SUPER = 2  # supersample for crisp edges
img = Image.new("RGB", (W * SUPER, H * SUPER), "#0b1020")
d = ImageDraw.Draw(img)
w, h = W * SUPER, H * SUPER

# --- vertical gradient background (deep navy -> slate) ---
top = (11, 16, 32)
bot = (23, 31, 56)
for y in range(h):
    t = y / h
    r = int(top[0] + (bot[0] - top[0]) * t)
    g = int(top[1] + (bot[1] - top[1]) * t)
    b = int(top[2] + (bot[2] - top[2]) * t)
    d.line([(0, y), (w, y)], fill=(r, g, b))

# --- soft glow on the right (lightmedia vibe) ---
glow = Image.new("RGB", (w, h), (0, 0, 0))
gd = ImageDraw.Draw(glow)
cx, cy = int(w * 0.82), int(h * 0.42)
maxr = int(h * 1.1)
for rr in range(maxr, 0, -4):
    t = rr / maxr
    col = (int(70 * (1 - t)), int(140 * (1 - t)), int(190 * (1 - t)))
    gd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)
# screen-blend the glow over the gradient (additive-style highlight)
from PIL import ImageChops
img = ImageChops.screen(img, glow)
d = ImageDraw.Draw(img)

# --- accent bar on the left ---
bar_x = int(w * 0.06)
d.rectangle([bar_x, int(h * 0.30), bar_x + 10 * SUPER, int(h * 0.72)], fill="#4fd1e0")

def font(path, size):
    return ImageFont.truetype(path, size * SUPER)

KARLA_REG  = str(ASSETS / "fonts" / "Karla-Regular.ttf")
KARLA_BOLD = str(ASSETS / "fonts" / "Karla-Bold.ttf")
f_kicker = font(KARLA_BOLD, 30)
f_title = font(KARLA_BOLD, 96)
f_date = font(KARLA_REG, 34)

tx = bar_x + 34 * SUPER

# kicker
d.text((tx, int(h * 0.28)), "Eos Lightmedia", font=f_kicker, fill="#8aa0c8")

# title
d.text((tx, int(h * 0.40)), "NGS Daily Digest", font=f_title, fill="#ffffff")

# date
d.text((tx, int(h * 0.70)), "Friday, June 12, 2026", font=f_date, fill="#4fd1e0")

# downscale for crisp anti-aliased result
img = img.resize((W, H), Image.LANCZOS)
out = str(BASE / "ngs_digest_banner.png")
img.save(out)
print("saved", out)
