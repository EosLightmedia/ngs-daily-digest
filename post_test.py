#!/usr/bin/env python3
"""One-off test: post today's Block Kit digest + upload the image card."""
import os
from slack_sdk import WebClient

import config
import schedule_reader as sr
import slack_digest
from digest import today_in_tz

IMAGE = "/Users/oonacurley/Desktop/claude/NGS/ngs_digest_card.png"

target = today_in_tz()
header, data = sr.load_rows()
block = sr.find_block(sr.parse_blocks(header, data), target)
if block is None:
    raise SystemExit(f"No schedule block for {target} — nothing to post.")

blocks, fallback = slack_digest.build_blocks(block)
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

msg = client.chat_postMessage(channel=config.SLACK_CHANNEL_ID, blocks=blocks,
                              text=f"[TEST] {fallback}")
print("message ts:", msg["ts"])

up = client.files_upload_v2(
    channel=config.SLACK_CHANNEL_ID,
    file=IMAGE,
    title=f"NGS Daily Digest — {target:%b %-d}",
    initial_comment="_(test) image version of the digest_",
)
f = up.get("file", {})
print("file id:", f.get("id"), "| name:", f.get("name"))
