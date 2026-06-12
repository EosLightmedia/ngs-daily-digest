#!/usr/bin/env python3
"""Render the NGS daily digest content as a shareable card (PNG + PDF)."""
from PIL import Image, ImageDraw, ImageFont, ImageChops

# ---- content (today's resolved digest) ----
TITLE_DATE = "Friday, June 12, 2026"
HEADLINE = "E2K Load-In / MOE Standard Operations"
SPAN = "10:00 AM – 9:00 PM"

SUPPORT = [
    ("Wonders of Our World Testing", "7:00 PM – 9:00 PM", "Courtyard, Pavilion"),
]

CREW = [
    ("Q-Sys",   "Joe (remote)",      "7:00 PM – 9:00 PM"),
    ("Pixera",  "Sam",               "7:00 PM – 9:00 PM"),
    ("Network", "Niko",              "7:00 PM – 9:00 PM"),
    ("Network", "Sean (on call)",    "9:00 PM"),
    ("Tech",    "Benjamin",          "7:00 PM – 9:00 PM"),
]

FOOTER = "Full detail in the production schedule."

# ---- style ----
S = 2  # supersample
W = 1240
PAD = 70 * S
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"

NAVY_T = (11, 16, 32)
NAVY_B = (23, 31, 56)
CYAN = (79, 209, 224)
INK = (28, 34, 48)
SUB = (110, 122, 145)
LINE = (224, 230, 240)
BG = (247, 249, 252)
BLUE = (43, 132, 222)

def F(sz, kind=0):
    return ImageFont.truetype(AVENIR, sz * S, index=kind)

f_kick   = F(26)
f_title  = F(64)
f_h      = F(30)
f_label  = F(26)
f_body   = F(30)
f_role   = F(28)
f_small  = F(24)

w = W * S

# measure-then-draw: compute total height first
HEADER_H = 230 * S
y = HEADER_H + 50 * S
# span row
y += 70 * S
# support
y += 50 * S + len(SUPPORT) * 78 * S + 30 * S
# crew
y += 50 * S + len(CREW) * 64 * S + 30 * S
# footer
y += 90 * S
H_TOTAL = y + PAD // 2

img = Image.new("RGB", (w, H_TOTAL), BG)
d = ImageDraw.Draw(img)

# ---- header gradient band ----
for yy in range(HEADER_H):
    t = yy / HEADER_H
    c = tuple(int(NAVY_T[i] + (NAVY_B[i] - NAVY_T[i]) * t) for i in range(3))
    d.line([(0, yy), (w, yy)], fill=c)
# glow
glow = Image.new("RGB", (w, HEADER_H), (0, 0, 0))
gd = ImageDraw.Draw(glow)
cx, cy, maxr = int(w * 0.86), int(HEADER_H * 0.4), int(HEADER_H * 1.4)
for rr in range(maxr, 0, -4):
    t = rr / maxr
    gd.ellipse([cx-rr, cy-rr, cx+rr, cy+rr],
               fill=(int(60*(1-t)), int(120*(1-t)), int(165*(1-t))))
band = ImageChops.screen(img.crop((0, 0, w, HEADER_H)), glow)
img.paste(band, (0, 0))
d = ImageDraw.Draw(img)

# accent bar + header text
d.rectangle([PAD, 70*S, PAD + 9*S, 175*S], fill=CYAN)
tx = PAD + 32*S
d.text((tx, 66*S), "NGS DAILY DIGEST", font=f_kick, fill=(138, 160, 200))
d.text((tx, 100*S), TITLE_DATE, font=f_title, fill=(255, 255, 255))

# ---- headline strip ----
y = HEADER_H + 44*S
d.text((PAD, y), HEADLINE, font=f_h, fill=INK)
y += 58*S

# span-of-day pill
pill = f"Span of Day   {SPAN}"
bb = d.textbbox((0, 0), pill, font=f_label)
pw, ph = bb[2]-bb[0], bb[3]-bb[1]
d.rounded_rectangle([PAD, y, PAD + pw + 56*S, y + ph + 30*S], radius=22*S,
                    fill=(233, 246, 249))
d.text((PAD + 28*S, y + 13*S), pill, font=f_label, fill=(20, 110, 125))
y += ph + 30*S + 52*S

def section_title(yy, text, dot=None):
    if dot:
        r = 11*S
        d.ellipse([PAD, yy+6*S, PAD+2*r, yy+6*S+2*r], fill=dot)
        d.text((PAD + 3*r + 6*S, yy), text, font=f_h, fill=INK)
    else:
        d.text((PAD, yy), text, font=f_h, fill=INK)
    return yy + 56*S

# ---- support required ----
y = section_title(y, "Support Required", dot=BLUE)
for name, time, loc in SUPPORT:
    d.text((PAD, y), name, font=f_body, fill=INK)
    d.text((PAD, y + 38*S), f"{time}   ·   {loc}", font=f_small, fill=SUB)
    y += 78*S
y += 30*S

# divider
d.line([(PAD, y), (w - PAD, y)], fill=LINE, width=2*S)
y += 44*S

# ---- crew call (table) ----
y = section_title(y, "Crew Call")
role_x = PAD
name_x = PAD + 210*S
time_x = w - PAD - 340*S
for role, name, time in CREW:
    d.text((role_x, y), role, font=f_role, fill=CYAN if False else (20, 110, 125))
    d.text((name_x, y), name, font=f_body, fill=INK)
    d.text((time_x, y), time, font=f_small, fill=SUB)
    y += 64*S
y += 30*S

# ---- footer ----
d.line([(PAD, y), (w - PAD, y)], fill=LINE, width=2*S)
y += 30*S
d.text((PAD, y), FOOTER, font=f_small, fill=SUB)

# downscale + export
final = img.resize((W, H_TOTAL // S), Image.LANCZOS)
png = "/Users/oonacurley/Desktop/claude/NGS/ngs_digest_card.png"
pdf = "/Users/oonacurley/Desktop/claude/NGS/ngs_digest_card.pdf"
final.save(png)
final.convert("RGB").save(pdf, "PDF", resolution=150)
print("saved", png)
print("saved", pdf)
