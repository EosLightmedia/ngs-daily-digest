#!/usr/bin/env python3
"""NGS Daily Digest — read the production schedule and post a morning summary to Slack.

Usage:
    python digest.py                         # today (America/New_York), post to Slack
    python digest.py --date 2026-06-13       # a specific day
    python digest.py --dry-run               # print Block Kit JSON, post nothing
    python digest.py --channel C0XXXX        # override target channel

If no day-block matches the target date (i.e. we're outside the event window),
nothing is posted — this keeps the channel quiet off-season.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import config
import schedule_reader as sr
import slack_digest


def today_in_tz() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def main() -> int:
    ap = argparse.ArgumentParser(description="Post the NGS daily digest to Slack.")
    ap.add_argument("--date", help="YYYY-MM-DD to report (default: today in event timezone)")
    ap.add_argument("--channel", default=config.SLACK_CHANNEL_ID, help="Slack channel ID")
    ap.add_argument("--dry-run", action="store_true", help="print blocks JSON, do not post")
    args = ap.parse_args()

    target = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else today_in_tz()

    header, data = sr.load_rows()
    blocks_data = sr.parse_blocks(header, data)
    block = sr.find_block(blocks_data, target)

    if block is None:
        print(f"No schedule block for {target.isoformat()} — outside event window. Skipping.")
        return 0

    blocks, fallback = slack_digest.build_blocks(block)

    if args.dry_run:
        print(json.dumps({"channel": args.channel, "text": fallback, "blocks": blocks}, indent=2))
        return 0

    resp = slack_digest.post(blocks, fallback, args.channel)
    print(f"Posted to {args.channel}: ts={resp.get('ts')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
