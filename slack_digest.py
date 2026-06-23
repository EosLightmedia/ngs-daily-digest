"""Turn a parsed DayBlock into Slack Block Kit and post it.

Sections are independent builder functions so future additions (Needs
Confirmation alerts, VIP movements, multi-day look-aheads, …) are purely
additive — append another builder in `build_blocks`.
"""
from __future__ import annotations

import calendar
import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import schedule_reader as sr

_STAFF_MAP_PATH = Path(__file__).with_name("staff_slack_ids.json")
_CC_MAP_PATH = Path(__file__).with_name("cc_slack_ids.json")


# --------------------------------------------------------------------------- #
# Staff @-mentions
# --------------------------------------------------------------------------- #
def _load_staff_map() -> dict[str, str]:
    if _STAFF_MAP_PATH.exists():
        return json.loads(_STAFF_MAP_PATH.read_text())
    return {}


def render_people(names: list[str], staff_map: dict[str, str] | None = None) -> str:
    """Render staff first-names as Slack @-mentions when we know their ID,
    otherwise as bold plain text."""
    if staff_map is None:
        staff_map = _load_staff_map()
    out = []
    for n in names:
        sid = staff_map.get(n) or staff_map.get(n.lower()) or staff_map.get(n.title())
        out.append(f"<@{sid}>" if sid else f"*{n}*")
    return ", ".join(out)


# --------------------------------------------------------------------------- #
# Image-post caption (the only text accompanying the one-page image)
# --------------------------------------------------------------------------- #
def _load_cc() -> dict[str, str]:
    if _CC_MAP_PATH.exists():
        return {k: v for k, v in json.loads(_CC_MAP_PATH.read_text()).items()
                if not k.startswith("_")}
    return {}


def crew_mentions(block: sr.DayBlock, staff_map: dict[str, str] | None = None) -> str:
    """@-mention every person called on any system today (de-duped, in order)."""
    names: list[str] = []
    for fn in sr.crew_call(block):
        if fn["label"] not in config.CREW_TAG_LABELS:
            continue  # Site Team / Management show in the grid but aren't tagged
        for p in fn["people"]:
            if p["name"] not in names:
                names.append(p["name"])
    return render_people(names, staff_map)


def build_image_caption(block: sr.DayBlock, staff_map: dict[str, str] | None = None,
                        note: str | None = None) -> str:
    """Caption that accompanies the day's image: optional note + who's called + CC."""
    lines: list[str] = []
    if note:
        lines.append(f"*{note}*")
    lines.append(f"*🗓️  {_schedule_heading(block)}*")
    crew = crew_mentions(block, staff_map)
    lines.append(f"Event Coverage: {crew}" if crew else "Event Coverage: _nobody scheduled_")
    cc = ", ".join(f"<@{sid}>" for sid in _load_cc().values())
    if cc:
        lines.append(f"CC: {cc}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Block helpers
# --------------------------------------------------------------------------- #
def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _header(text: str) -> dict:
    # header blocks are plain_text and capped at 150 chars
    return {"type": "header", "text": {"type": "plain_text", "text": text[:150], "emoji": True}}


def _divider() -> dict:
    return {"type": "divider"}


def _title(block: sr.DayBlock) -> str:
    if block.date:
        return f"{block.weekday}, {calendar.month_name[block.date.month]} {block.date.day}"
    return block.banner


def _schedule_heading(block: sr.DayBlock) -> str:
    """'Tomorrow's/Today's Schedule — <date>' when the block is the day after /
    of the run date (the scheduled evening-before post), else a plain dated
    'Schedule — <date>' so a manual back/forward-dated send reads correctly."""
    rel = "Schedule"
    if block.date:
        today = datetime.now(ZoneInfo(config.TIMEZONE)).date()
        delta = (block.date - today).days
        rel = {1: "Tomorrow’s Schedule", 0: "Today’s Schedule"}.get(delta, "Schedule")
    return f"{rel} — {_title(block)}"


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #
def build_blocks(block: sr.DayBlock, staff_map: dict[str, str] | None = None) -> tuple[list[dict], str]:
    """Return (blocks, fallback_text)."""
    if staff_map is None:
        staff_map = _load_staff_map()

    label_suffix = f": {block.label}" if block.label else ""
    blocks: list[dict] = [_header(f"🗓️  {_title(block)}{label_suffix}")]

    # --- First section: span, dress code, Support + Live Events ------------
    lines: list[str] = []

    span = sr.event_span(block)
    if span:
        lines.append(f"Span of Day: {span}")

    dress = sr.dress_code(block)
    if dress:
        lines.append(f"Dress code: *{dress}*")

    support = sr.rows_of_type(block, config.TYPE_SUPPORT)
    show_groups = sr.group_consecutive_shows(block)

    if support:
        lines.append(("\n" if lines else "") + "🔵  *Support*")
        for r in support:
            span_s = sr.fmt_span(sr.parse_time(r[config.COL_START]), sr.parse_time(r[config.COL_END]))
            loc = r[config.COL_LOCATION]
            line = f"• *{r[config.COL_ITEM]}*"
            if span_s:
                line += f"  · {span_s}"
            if loc:
                line += f"  · _{loc}_"
            lines.append(line)

    if show_groups:
        lines.append(("\n" if lines else "") + "🟢  *Live Events*")
        for g in show_groups:
            summary = " → ".join(g["items"]) if g["items"] else "Live Event"
            prefix = f"• *{g['span']}*  " if g["span"] else "• "
            lines.append(f"{prefix}{summary}")

    if not support and not show_groups:
        lines.append("_Nothing scheduled today._")
    blocks.append(_section("\n".join(lines)))

    # --- Event Coverage (who's on each system, and when) --------------------
    crew = sr.crew_call(block)
    if crew:
        lines = ["*🧑‍🔧  Event Coverage*"]
        for fn in crew:
            people = []
            for p in fn["people"]:
                who = render_people([p["name"]], staff_map)
                if p["qualifier"]:
                    who += f" _({p['qualifier']})_"
                people.append(f"{who} {p['span']}".strip())
            lines.append(f"*{fn['label']}*: " + ", ".join(people))
        blocks.append(_section("\n".join(lines)))

    # --- Staffing Notes (directly under Event Coverage) ---------------------
    notes = sr.staffing_notes(block)
    if notes:
        lines = ["*📝  Staffing Notes*"]
        lines += [f"• {n}" for n in notes] if len(notes) > 1 else [notes[0]]
        blocks.append(_section("\n".join(lines)))

    # --- Link to the sheet --------------------------------------------------
    blocks.append(_divider())
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*Full detail in the production schedule.*"},
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": "📋 Open the schedule", "emoji": True},
            "url": config.SHEET_URL,
        },
    })

    fallback = _title(block)
    return blocks, fallback


# --------------------------------------------------------------------------- #
# Posting
# --------------------------------------------------------------------------- #
def post(blocks: list[dict], fallback: str, channel: str) -> dict:
    """Post a Block Kit message via the bot token in SLACK_BOT_TOKEN.

    Retained for reference/testing; the live digest now posts an image instead.
    """
    from slack_sdk import WebClient

    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    resp = client.chat_postMessage(channel=channel, blocks=blocks, text=fallback)
    return resp.data


def upload_image(image_path, caption: str, channel: str,
                 title: str = "NGS Daily Digest") -> dict:
    """Upload the day's one-page image with its caption — this IS the post.

    Slack's upload endpoint occasionally returns a transient 5xx / times out
    (the scheduled run is the busiest moment on their CDN), which used to fail
    the whole job. Retry a few times with backoff so a single hiccup doesn't
    drop the day's digest.
    """
    import time
    import urllib.error

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    # Give the upload more room than the 30s default — a ~500 KB PNG over a
    # congested CDN can legitimately take a while.
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"], timeout=60)

    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            resp = client.files_upload_v2(channel=channel, file=str(image_path),
                                          title=title, initial_comment=caption)
            return resp.get("file", {})
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, ConnectionError, SlackApiError) as e:
            if attempt == attempts:
                raise
            wait = 2 ** attempt  # 2s, 4s, 8s
            print(f"Slack upload attempt {attempt}/{attempts} failed ({e!r}); "
                  f"retrying in {wait}s", flush=True)
            time.sleep(wait)
