"""Turn a parsed DayBlock into Slack Block Kit and post it.

Sections are independent builder functions so future additions (Needs
Confirmation alerts, VIP movements, multi-day look-aheads, …) are purely
additive — append another builder in `build_blocks`.
"""
from __future__ import annotations

import calendar
import json
import os
from datetime import date
from pathlib import Path

import config
import schedule_reader as sr

_STAFF_MAP_PATH = Path(__file__).with_name("staff_slack_ids.json")


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
        lines.append(("\n" if lines else "") + "🔵  *Support Required*")
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

    # --- Crew Call (who's on each system, and when) -------------------------
    crew = sr.crew_call(block)
    if crew:
        lines = ["*🧑‍🔧  Crew Call*"]
        for fn in crew:
            people = []
            for p in fn["people"]:
                who = render_people([p["name"]], staff_map)
                if p["qualifier"]:
                    who += f" _({p['qualifier']})_"
                people.append(f"{who} {p['span']}".strip())
            lines.append(f"*{fn['label']}*: " + ", ".join(people))
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
    """Post to Slack via the bot token in SLACK_BOT_TOKEN."""
    from slack_sdk import WebClient

    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    resp = client.chat_postMessage(channel=channel, blocks=blocks, text=fallback)
    return resp.data
