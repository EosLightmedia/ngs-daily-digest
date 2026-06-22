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
# Channel used by "Send test" from the Sheet menu. Defaults to the main channel
# so a misconfigured deploy is loud rather than silent; set TEST_CHANNEL_ID (env
# / GitHub repo variable) to a real test channel so test sends stay out of the
# live channel.
TEST_CHANNEL_ID = os.environ.get("TEST_CHANNEL_ID", SLACK_CHANNEL_ID)

# --- Header -----------------------------------------------------------------
# Optional contact line under the date in the card header. Empty = omit it.
HEADER_CONTACT_LINE = os.environ.get("NGS_HEADER_CONTACT", "")

# --- Pause switch -----------------------------------------------------------
# Named range in the sheet holding TRUE/FALSE. The Sheet menu's Pause/Resume
# writes it; the scheduled run reads it (digest.py --skip-if-paused) and skips
# posting when TRUE. Manual sends ignore it.
PAUSE_NAMED_RANGE = os.environ.get("NGS_PAUSE_RANGE", "DIGEST_PAUSED")

# --- Timezone ---------------------------------------------------------------
# "Today" is computed in this zone; the digest is meant for the East-coast crew.
TIMEZONE = os.environ.get("NGS_TIMEZONE", "America/New_York")

# --- Type values that drive each section ------------------------------------
# Compared case-insensitively against the live Type column.
TYPE_SPAN_MARKER = "Top/End of Day"     # grey rows that bound the day
TYPE_SUPPORT = "Support"                # blue rows that need the team on-site
TYPE_SHOW = "Show"                      # green rows
TYPE_SHIFT = "Shift"                    # tech-coverage shifts: hidden from the
                                        # line-by-line agenda; a shift row defines
                                        # that person's Crew Call window

# --- Column header names (the canonical labels we expect in HEADER_ROW) ------
COL_DATE = "Date"
COL_START = "Start"
COL_END = "End"
COL_LOCATION = "Location"
COL_ITEM = "Item"
COL_NOTES = "Notes"
COL_TYPE = "Type"
COL_OWNER = "Owner"
COL_DRESS_CODE = "Dress Code"

# --- Crew staffing columns --------------------------------------------------
# Staffing is no longer dedicated "shift" rows; instead each row carries the
# people on each function/system in its own column. The digest scans these
# across the day and reports, per system, who is on it and their day-span.
# (header_name_in_sheet, display_label). Resolved by name; missing ones are
# skipped, so reordering/renaming a system here is the only edit needed.
STAFF_FUNCTION_COLS = [
    ("Qsys", "Q-Sys"),
    ("Pixera", "Pixera"),
    ("Network", "Network"),
    ("Tech", "Tech"),
    ("Site Team", "Site Team"),
    ("Management", "Management"),
]

# Functions whose people are @-tagged in the "Crew called:" caption line. The
# others (Site Team, Management) still render in the Crew Call grid for
# reference, but aren't auto-tagged — Management is covered by the CC list.
CREW_TAG_LABELS = {"Q-Sys", "Pixera", "Network", "Tech"}

# --- Formatting lint --------------------------------------------------------
# Recognised Type values (sheet_lint flags any Type cell outside this set so a
# typo like "Suppot" can't silently drop a row from the digest). Derived from
# the TYPE_* drivers above plus the everyday values the sheet uses.
KNOWN_TYPES = {
    TYPE_SPAN_MARKER, TYPE_SUPPORT, TYPE_SHOW, TYPE_SHIFT, "Break",
}
# Recognised Location values, if you want Location linted too. Empty = skip the
# Location check (locations change often; leave unset until the zone list is
# stable). Populate with the sheet's zone names to enable it.
KNOWN_LOCATIONS: set[str] = set()
