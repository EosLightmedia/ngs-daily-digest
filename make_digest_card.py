#!/usr/bin/env python3
"""Render the NGS daily digest as a one-page, full-bleed Letter card.

Reads the live production schedule (same source as the Slack digest) and lays
out every event for the day — except Top/End of Day markers and Breaks — as a
chronological list, with Crew Call up top. Support and Show rows stay
visually prominent (tinted row + coloured dot + bold), matching the 🔵/🟢
convention in Slack.

The whole thing is fit onto ONE full-bleed 8.5x11 (portrait) page: the layout is
rendered at a scale chosen so the day's content exactly fills a single page. Busy
days render denser; light days keep full-size type with whitespace below. Never
scales up past the natural design size.

Outputs:
    ngs_digest_card.png   — full-bleed Letter-aspect image (post this to Slack)
    ngs_digest_card.pdf   — same, single Letter page (for printing)

Usage:
    python make_digest_card.py                 # today (event timezone)
    python make_digest_card.py --date 2026-06-16
"""
from __future__ import annotations

import argparse
import calendar
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageChops

import config
import schedule_reader as sr

# --------------------------------------------------------------------------- #
# Content — pulled live from the schedule
# --------------------------------------------------------------------------- #
ap = argparse.ArgumentParser(description="Render the NGS daily digest card.")
ap.add_argument("--date", help="YYYY-MM-DD (default: today in event timezone)")
args = ap.parse_args()

target = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
          else datetime.now(ZoneInfo(config.TIMEZONE)).date())

header, data = sr.load_rows()
block = sr.find_block(sr.parse_blocks(header, data), target)
if block is None:
    raise SystemExit(f"No schedule block for {target} — nothing to render.")

TITLE_DATE = f"{block.weekday}, {calendar.month_name[block.date.month]} {block.date.day}"
HEADLINE = block.label or block.banner
SPAN = sr.event_span(block)

# Every row except day-bounding markers, breaks, and shift rows, in time order.
# (Shift rows staff Crew Call but don't belong in the line-by-line agenda.)
EXCLUDE = {config.TYPE_SPAN_MARKER.lower(), "break", config.TYPE_SHIFT.lower()}

def kind_of(type_value: str) -> str:
    tl = type_value.strip().lower()
    if tl == config.TYPE_SUPPORT.lower():
        return "support"
    if tl == config.TYPE_SHOW.lower():
        return "show"
    return "other"

EVENTS = []
for r in block.rows:
    if r[config.COL_TYPE].strip().lower() in EXCLUDE:
        continue
    start = sr.parse_time(r[config.COL_START])
    end = sr.parse_time(r[config.COL_END])
    EVENTS.append({
        "time": sr.fmt_span(start, end),
        "item": r[config.COL_ITEM] or "—",
        "loc": r[config.COL_LOCATION],
        "kind": kind_of(r[config.COL_TYPE]),
        "_sort": start if start is not None else 24 * 60 * 10,
    })
EVENTS.sort(key=lambda e: (e["_sort"], e["item"]))

# Keep crew grouped by function so each system gets its own column. We iterate
# config.STAFF_FUNCTION_COLS (Q-Sys, Pixera, Network, Tech) so all four columns
# always show in order, even if a system has nobody called that day.
_crew_groups = {fn["label"]: fn["people"] for fn in sr.crew_call(block)}
CREW_BY_FN = []
for _hdr, _label in config.STAFF_FUNCTION_COLS:
    people = [(p["name"] + (f" ({p['qualifier']})" if p["qualifier"] else ""), p["span"])
              for p in _crew_groups.get(_label, [])]
    CREW_BY_FN.append((_label, people))

FOOTER = "Full detail in the production schedule."

# --------------------------------------------------------------------------- #
# Style
# --------------------------------------------------------------------------- #
SS = 2                 # supersample factor (fixed; downscaled on export)
W = 1240               # logical page width in output px
w = W * SS             # render width (stays constant — full bleed, never scaled)
PAGE_ASPECT = 11 / 8.5 # Letter, portrait (height / width)
TARGET_H = w * PAGE_ASPECT

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"
KARLA_REG  = str(ASSETS / "fonts" / "Karla-Regular.ttf")
KARLA_BOLD = str(ASSETS / "fonts" / "Karla-Bold.ttf")

BLACK  = (0, 0, 0)        # NGS brand
GOLD   = (255, 204, 0)    # NGS brand #FFCC00
LOGO_PATH = str(ASSETS / "ngs-logo.png")
EOS_LOGO_PATH = str(ASSETS / "eos-logo-vertical.png")
INK    = (28, 34, 48)
SUB    = (110, 122, 145)
LINE   = (224, 230, 240)
BG     = (255, 255, 255)
TEAL   = (20, 110, 125)
BLUE   = (43, 132, 222)
GREEN  = (34, 168, 108)
BLUE_BG  = (231, 240, 252)
GREEN_BG = (230, 247, 238)
DOT_GREY = (184, 193, 207)
CHIP_BG  = (255, 238, 184)   # warm gold chip for call times
CHIP_INK = (92, 70, 0)       # dark gold text on the chip
PILL_BG  = (233, 246, 249)


def render(K):
    """Draw the whole card at design-scale K. Width is fixed (w); only type
    sizes and vertical/inner spacing scale with K. Returns (img, content_bottom)."""
    S = SS * K
    def I(v):
        return int(round(v))
    def F(sz, bold=False):
        return ImageFont.truetype(KARLA_BOLD if bold else KARLA_REG, max(6, I(sz * S)))

    f_kick   = F(26, bold=True)
    f_title  = F(64, bold=True)
    f_contact = F(20)             # header footer: event-coordinator contact line
    f_h      = F(30, bold=True)
    f_label  = F(26, bold=True)
    f_body   = F(30)
    f_body_b = F(30, bold=True)
    f_role   = F(28, bold=True)
    f_time   = F(26)
    f_time_b = F(21, bold=True)
    f_small  = F(24)
    f_crew_h = F(22, bold=True)   # crew stripe: function label
    f_crew   = F(23, bold=True)   # crew stripe: person name
    f_chip   = F(19, bold=True)   # crew stripe: compact call-time chip

    PAD = 70 * S
    HEADER_H = I(230 * S)
    H_MAX = I(HEADER_H + (len(EVENTS) + 24) * 90 * S)
    img = Image.new("RGB", (w, H_MAX), BG)
    d = ImageDraw.Draw(img)

    # ---- header: black -> #FFCC00 gradient (eased so the text zone stays dark) ----
    for xx in range(w):
        t = (xx / w) ** 2.2
        d.line([(xx, 0), (xx, HEADER_H)],
               fill=tuple(int(BLACK[i] + (GOLD[i] - BLACK[i]) * t) for i in range(3)))
    glow = Image.new("RGB", (w, HEADER_H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy, maxr = I(w * 0.88), I(HEADER_H * 0.42), I(HEADER_H * 1.2)
    for rr in range(maxr, 0, -4):
        t = rr / maxr
        gd.ellipse([cx-rr, cy-rr, cx+rr, cy+rr],
                   fill=(int(120*(1-t)), int(96*(1-t)), int(8*(1-t))))
    img.paste(ImageChops.screen(img.crop((0, 0, w, HEADER_H)), glow), (0, 0))
    d = ImageDraw.Draw(img)

    # NGS logo (its black field blends into the dark left of the header)
    logo_h = I(150 * S)
    logo = Image.open(LOGO_PATH).convert("RGBA").resize((logo_h, logo_h), Image.LANCZOS)
    img.paste(logo, (I(PAD), (HEADER_H - logo_h)//2), logo)

    # Eos Lightmedia logo (vertical) on the gold side — placed first so the date
    # can be clamped to its left edge and never collide with it.
    eos = Image.open(EOS_LOGO_PATH).convert("RGBA")
    eos_h = I(168 * S)
    eos_w = I(eos.width * eos_h / eos.height)
    eos = eos.resize((eos_w, eos_h), Image.LANCZOS)
    eos_x = w - I(PAD) - eos_w
    img.paste(eos, (eos_x, (HEADER_H - eos_h)//2), eos)
    d = ImageDraw.Draw(img)

    tx = PAD + logo_h + 40*S
    d.text((tx, 66*S), "NGS DAILY DIGEST", font=f_kick, fill=GOLD)
    # Shrink the date so it fits the gap between the kicker and the Eos logo
    # (big-type, few-event days would otherwise run the date under the logo).
    tf, tsz = f_title, 64
    title_max = eos_x - tx - 30*S
    while tsz > 28 and d.textlength(TITLE_DATE, font=tf) > title_max:
        tsz -= 2; tf = F(tsz, bold=True)
    d.text((tx, 100*S), TITLE_DATE, font=tf, fill=(255, 255, 255))
    # Optional contact line pinned to the bottom of the header band, under the
    # date. Driven by config.HEADER_CONTACT_LINE — empty (the default) omits it.
    if config.HEADER_CONTACT_LINE:
        d.text((tx, HEADER_H - 44*S), config.HEADER_CONTACT_LINE,
               font=f_contact, fill=(230, 235, 244))

    # ---- headline + span pill (same row; pill right-aligned) ----
    # Lay out the pill first so the day label can be clamped to the space left
    # of it (otherwise a long label + big type overruns the pill).
    y = HEADER_H + 44*S
    head_max = w - 2*PAD
    pill = pill_x = pill_y = pill_w = ph = None
    if SPAN:
        pill = f"Span of Day   {SPAN}"
        bb = d.textbbox((0, 0), pill, font=f_label)
        pw, ph = bb[2]-bb[0], bb[3]-bb[1]
        pill_w = pw + 56*S
        pill_x = w - PAD - pill_w
        pill_y = y - 8*S
        head_max = pill_x - PAD - 30*S
    # Shrink the day label to fit, then ellipsize if still too long.
    hf, hsz = f_h, 30
    while hsz > 15 and d.textlength(HEADLINE, font=hf) > head_max:
        hsz -= 1; hf = F(hsz, bold=True)
    htext = HEADLINE
    if d.textlength(htext, font=hf) > head_max:
        while htext and d.textlength(htext + "…", font=hf) > head_max:
            htext = htext[:-1]
        htext = (htext + "…") if htext else HEADLINE
    d.text((PAD, y), htext, font=hf, fill=INK)
    if SPAN:
        d.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + ph + 30*S],
                            radius=22*S, fill=PILL_BG)
        d.text((pill_x + 28*S, pill_y + 13*S), pill, font=f_label, fill=TEAL)
    y += 66*S

    def section_title(yy, text):
        d.text((PAD, yy), text, font=f_h, fill=INK)
        return yy + 56*S

    def wrap(text, font, max_w):
        lines, cur = [], ""
        for wd in text.split():
            trial = f"{cur} {wd}".strip()
            if not cur or d.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines or [""]

    # ---- crew call (top): a single staffing stripe — every function in one row,
    #      people stacked beneath each, with compact call-time chips. ----
    def compact_time(span):
        # "9:00 AM – 4:00 PM" -> "9a–4p" ; "7:30 PM – 8:30 PM" -> "7:30p–8:30p"
        return (span.replace(":00", "").replace(" AM", "a").replace(" PM", "p")
                    .replace(" – ", "–")) or "TBD"

    if CREW_BY_FN:
        y = section_title(y, "Crew Coverage")
        cols = len(CREW_BY_FN)            # all systems on one stripe
        col_w = (w - 2*PAD) / cols
        gutter = 18*S                     # keep a name from butting into the next column
        name_max = col_w - gutter
        head_h = 36*S
        asc, desc = f_crew.getmetrics()
        name_line_h = asc + desc + I(2*S)
        chip_h = 26*S
        slot_gap = 18*S                   # vertical space between stacked people
        crew_top = y

        def fit_name(text):
            """Wrap a crew name to <=2 lines within the column; ellipsize if it
            still overflows so it can never spill into the neighbouring column."""
            lines = wrap(text, f_crew, name_max)
            if len(lines) <= 2:
                return lines
            rest = " ".join(lines[1:])
            while rest and d.textlength(rest + "…", font=f_crew) > name_max:
                rest = rest[:-1]
            return [lines[0], (rest + "…") if rest else lines[1]]

        # Pre-wrap every name, then give each row the height of its tallest cell
        # so columns stay aligned and nothing overlaps vertically or sideways.
        prepped = [[(fit_name(n), t) for n, t in people] for _, people in CREW_BY_FN]
        max_people = max((len(p) for p in prepped), default=0)
        row_y, ry = [], crew_top + head_h
        for r in range(max_people):
            nlines = max((len(prepped[c][r][0]) for c in range(cols)
                          if r < len(prepped[c])), default=1)
            row_y.append(ry)
            ry += nlines*name_line_h + 2*S + chip_h + slot_gap

        for ci, (label, _people) in enumerate(CREW_BY_FN):
            x = PAD + ci * col_w
            d.text((x, crew_top), label, font=f_crew_h, fill=TEAL)
            if not prepped[ci]:
                d.text((x, crew_top + head_h), "—", font=f_crew, fill=SUB)
                continue
            for r, (lines, time) in enumerate(prepped[ci]):
                py = row_y[r]
                for li, ln in enumerate(lines):
                    d.text((x, py + li*name_line_h), ln, font=f_crew, fill=INK)
                cy = py + len(lines)*name_line_h + 2*S
                ct = compact_time(time)
                tw = d.textlength(ct, font=f_chip)
                d.rounded_rectangle([x, cy, x + tw + 16*S, cy + chip_h],
                                    radius=7*S, fill=CHIP_BG)
                d.text((x + 8*S, cy + 3*S), ct, font=f_chip, fill=CHIP_INK)
        # Section bottom = end of the last row (drop the trailing slot gap).
        y = (ry - slot_gap if max_people else crew_top + head_h + name_line_h) + 14*S
        d.line([(PAD, y), (w - PAD, y)], fill=LINE, width=max(1, I(2*S)))
        y += 44*S

    # ---- today's schedule (all events; wraps long titles/locations) ----
    y = section_title(y, "Today’s Schedule")
    time_x = PAD + 46*S
    item_x = PAD + 340*S
    content_w = (w - PAD) - item_x

    if not EVENTS:
        d.text((PAD, y), "Nothing scheduled today.", font=f_body, fill=SUB)
        y += 56*S

    for e in EVENTS:
        kind = e["kind"]
        item_font = f_body_b if kind in ("support", "show") else f_body
        dot = {"support": BLUE, "show": GREEN}.get(kind, DOT_GREY)
        tint = {"support": BLUE_BG, "show": GREEN_BG}.get(kind)

        item_w = d.textlength(e["item"], font=item_font)
        loc_text = f"·  {e['loc']}" if e["loc"] else ""
        loc_w = d.textlength(loc_text, font=f_small) if loc_text else 0
        single = item_w + (22*S + loc_w if loc_text else 0) <= content_w

        if single:
            block_h = 46*S
        else:
            item_lines = wrap(e["item"], item_font, content_w)
            loc_lines = wrap(loc_text, f_small, content_w) if loc_text else []
            block_h = len(item_lines)*40*S + len(loc_lines)*34*S + 8*S

        if tint:
            d.rounded_rectangle([PAD, y-4*S, w-PAD, y+block_h-4*S], radius=14*S, fill=tint)

        rdot = 7*S
        d.ellipse([PAD+18*S-rdot, y+20*S-rdot, PAD+18*S+rdot, y+20*S+rdot], fill=dot)
        if e["time"]:
            d.text((time_x, y+6*S), e["time"], font=f_time, fill=TEAL)

        if single:
            d.text((item_x, y+4*S), e["item"], font=item_font, fill=INK)
            if loc_text:
                d.text((item_x + item_w + 22*S, y+8*S), loc_text, font=f_small, fill=SUB)
        else:
            ty = y + 4*S
            for ln in item_lines:
                d.text((item_x, ty), ln, font=item_font, fill=INK)
                ty += 40*S
            for ln in loc_lines:
                d.text((item_x, ty), ln, font=f_small, fill=SUB)
                ty += 34*S

        y += block_h + 16*S

    # ---- footer ----
    y += 14*S
    d.line([(PAD, y), (w - PAD, y)], fill=LINE, width=max(1, I(2*S)))
    y += 30*S
    d.text((PAD, y), FOOTER, font=f_small, fill=SUB)
    y += 50*S

    return img, y


# --------------------------------------------------------------------------- #
# Fit to one full-bleed Letter page
# --------------------------------------------------------------------------- #
# Pick the LARGEST scale whose content still fits one page height, so the day
# fills the page instead of leaving slack at the bottom. Content height is
# non-linear in K (text re-wraps as type resizes), so we binary-search for the
# fit rather than assume proportionality — the old proportional shrink overshot
# and left ~20% of the page empty even while type was scaled well below natural
# size. K_MAX caps growth so a near-empty schedule doesn't balloon the type.
K_MIN, K_MAX = 0.2, 1.6
lo, hi = K_MIN, K_MAX
for _ in range(16):
    K = (lo + hi) / 2
    _, cb = render(K)
    if cb <= TARGET_H:
        lo = K
    else:
        hi = K
K = lo
img, cb = render(K)

page_h = int(round(TARGET_H))
page = Image.new("RGB", (w, page_h), BG)
page.paste(img.crop((0, 0, w, min(int(round(cb)), page_h))), (0, 0))

png = str(BASE / "ngs_digest_card.png")
pdf = str(BASE / "ngs_digest_card.pdf")

# PNG for Slack (downscaled to logical width; full-bleed Letter aspect)
out = page.resize((W, int(round(page_h / SS))), Image.LANCZOS)
out.save(png)
# Single full-bleed Letter page PDF for printing (sized via PDF resolution)
page.save(pdf, "PDF", resolution=w / 8.5)
print(f"saved {png}  ({W}x{int(round(page_h/SS))}px, fit scale {K:.2f})")
print(f"saved {pdf}  (1 Letter page, full bleed)")
