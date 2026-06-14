#!/usr/bin/env python3
"""NGS Daily Digest — render the day's one-page schedule image and post it to Slack.

The post is image-only: the full-bleed Letter card (make_digest_card.py) carrying
the day's Crew Call + full schedule, plus a two-line caption —
    Crew called: <everyone on the doc>
    CC: <standing distribution list>
(See slack_digest.build_image_caption / cc_slack_ids.json.)

Usage:
    python digest.py                         # today (America/New_York), post to Slack
    python digest.py --date 2026-06-13       # a specific day
    python digest.py --dry-run               # render + print caption, post nothing
    python digest.py --channel C0XXXX        # override target channel

If no day-block matches the target date (i.e. we're outside the event window),
nothing is posted — this keeps the channel quiet off-season.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import schedule_reader as sr
import slack_digest

BASE = Path(__file__).resolve().parent
CARD_SCRIPT = BASE / "make_digest_card.py"
CARD_PNG = BASE / "ngs_digest_card.png"


def today_in_tz() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def render_card(target: date) -> Path:
    """Render the one-page card for `target` (writes CARD_PNG) and return its path."""
    subprocess.run(
        [sys.executable, str(CARD_SCRIPT), "--date", target.isoformat()],
        check=True,
    )
    return CARD_PNG


def main() -> int:
    ap = argparse.ArgumentParser(description="Post the NGS daily digest image to Slack.")
    ap.add_argument("--date", help="YYYY-MM-DD to report (default: today in event timezone)")
    ap.add_argument("--channel", default=config.SLACK_CHANNEL_ID, help="Slack channel ID")
    ap.add_argument("--note", help="optional bold note prepended to the caption (e.g. UPDATED)")
    ap.add_argument("--dry-run", action="store_true", help="render + print caption, post nothing")
    args = ap.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else today_in_tz()

    block = sr.find_block(sr.parse_blocks(*sr.load_rows()), target)
    if block is None:
        print(f"No schedule block for {target.isoformat()} — outside event window. Skipping.")
        return 0

    caption = slack_digest.build_image_caption(block, note=args.note)
    title = f"NGS Daily Digest — {block.weekday}, {target:%b %-d}"

    if args.dry_run:
        png = render_card(target)
        print(f"[dry-run] would upload {png}\n  title: {title}\n  caption:\n{caption}")
        return 0

    png = render_card(target)
    f = slack_digest.upload_image(png, caption, args.channel, title=title)
    print(f"Posted image to {args.channel}: file={f.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
