"""Central config for the NGS daily digest.

Everything here is env-overridable so the GitHub Actions workflow (and local
testing) can change behaviour without code edits. This is the single place to
tweak the channel, the source sheet, the timezone, and which Type values drive
each digest section.
"""
import os

# --- Source sheet -----------------------------------------------------------
SHEET_KEY = os.environ.get("NGS_SHEET_KEY", "1rSobFoD1zVCpOVWUpcwgY14d2fNRvk_Z_78PDS0q6R0")
SCHEDULE_TAB = os.environ.get("NGS_SCHEDULE_TAB", "Schedule")
# Public link surfaced in the digest so people can open the sheet for detail.
SHEET_URL = os.environ.get(
    "NGS_SHEET_URL",
    f"https://docs.google.com/spreadsheets/d/{SHEET_KEY}/edit#gid=482396219",
)

# Row 3 holds the headers (row 1 = title, row 2 = KEY strip). Columns are
# resolved by NAME, never by letter — Oona reorders columns between sessions.
HEADER_ROW = int(os.environ.get("NGS_HEADER_ROW", "3"))

# --- Slack ------------------------------------------------------------------
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "C0B9YCS6ALR")

# --- Timezone ---------------------------------------------------------------
# "Today" is computed in this zone; the digest is meant for the East-coast crew.
TIMEZONE = os.environ.get("NGS_TIMEZONE", "America/New_York")

# --- Type values that drive each section ------------------------------------
# Compared case-insensitively against the live Type column.
TYPE_SPAN_MARKER = "Top/End of Day"     # grey rows that bound the day
TYPE_SUPPORT = "Support Required"       # blue rows that need the team on-site
TYPE_SHOW = "Show"                      # green rows
TYPE_STAFF_SHIFT = "Eos staff shifts"   # yellow rows; people listed in "Eos Staff" col

# --- Column header names (the canonical labels we expect in HEADER_ROW) ------
COL_DATE = "Date"
COL_START = "Start"
COL_END = "End"
COL_LOCATION = "Location"
COL_ITEM = "Item"
COL_NOTES = "Notes"
COL_TYPE = "Type"
COL_DISCIPLINE = "Discipline"
COL_OWNER = "Owner"
COL_EOS_STAFF = "Eos Staff"
COL_DRESS_CODE = "Dress Code"
