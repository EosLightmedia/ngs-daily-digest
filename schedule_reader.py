"""Read and parse the NGS production schedule.

Everything in here is header-NAME based (never fixed column letters) because the
sheet's columns get reordered between sessions. The schedule is organised as
per-day blocks separated by charcoal "banner" rows whose first cell is a weekday
name (e.g. "Thursday, June 11 - DESTINATION DC EVENT").
"""
from __future__ import annotations

import calendar
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date

import config

WEEKDAYS = {d.lower() for d in calendar.day_name}            # monday..sunday
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}  # january->1
# Default year for the event window; the sheet carries no year of its own.
DEFAULT_YEAR = int(os.environ.get("NGS_EVENT_YEAR", "2026"))


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class DayBlock:
    date: date | None          # calendar date parsed from the banner (year = DEFAULT_YEAR)
    weekday: str               # "Thursday"
    label: str                 # sub-context after the date, e.g. "DESTINATION DC EVENT"
    banner: str                # the raw banner text
    rows: list[dict] = field(default_factory=list)  # data rows, each keyed by column name


# --------------------------------------------------------------------------- #
# Sheet access
# --------------------------------------------------------------------------- #
def _client():
    """Authorise gspread (imported lazily so parsing works without it/creds).

    In CI the full service-account JSON is provided in GSPREAD_SERVICE_ACCOUNT;
    locally we fall back to the key at ~/.config/gspread/service_account.json.
    """
    import gspread

    raw = os.environ.get("GSPREAD_SERVICE_ACCOUNT")
    if raw:
        return gspread.service_account_from_dict(json.loads(raw))
    return gspread.service_account()


def _detect_header_row(values: list[list[str]]) -> int:
    """Return the 0-based index of the header row, found by its column names so
    it survives the sheet being shifted up/down (rows inserted above it).

    The header is the row carrying the canonical labels; we match on a few that
    are always present (Date/Start/Type). Falls back to config.HEADER_ROW.
    """
    want = {config.COL_DATE.lower(), config.COL_START.lower(), config.COL_TYPE.lower()}
    for idx, row in enumerate(values):
        if want.issubset({c.strip().lower() for c in row}):
            return idx
    return config.HEADER_ROW - 1


def load_rows() -> tuple[list[str], list[list[str]]]:
    """Return (header, data_rows) where data_rows are the rows BELOW the header.

    The header row is located by its column names rather than a fixed row
    number, so inserting/removing rows above it won't break column resolution.
    config.HEADER_ROW is only a fallback hint.
    """
    gc = _client()
    ws = gc.open_by_key(config.SHEET_KEY).worksheet(config.SCHEDULE_TAB)
    values = ws.get_all_values()
    h = _detect_header_row(values)
    return values[h], values[h + 1:]


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _col_index(header: list[str], name: str) -> int:
    """Resolve a column by its header name (case/space-insensitive)."""
    norm = [h.strip().lower() for h in header]
    try:
        return norm.index(name.strip().lower())
    except ValueError:
        raise KeyError(f"Column {name!r} not found in header {header!r}")


def _is_banner(first_cell: str) -> bool:
    """A banner row's first cell starts with a weekday name."""
    if not first_cell:
        return False
    token = re.split(r"[,\s]+", first_cell.strip())[0].lower()
    return token in WEEKDAYS


def _parse_banner(text: str) -> tuple[date | None, str, str]:
    """Return (date, weekday, label) from a banner like
    'Thursday, June 11 - DESTINATION DC EVENT'."""
    weekday = re.split(r"[,\s]+", text.strip())[0]
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})", text)
    parsed = None
    if m and m.group(1).lower() in MONTHS:
        parsed = date(DEFAULT_YEAR, MONTHS[m.group(1).lower()], int(m.group(2)))
    # Label = anything after a " - " / "—" separator.
    label = ""
    sep = re.split(r"\s[-–—]\s", text, maxsplit=1)
    if len(sep) > 1:
        label = sep[1].strip()
    return parsed, weekday, label


def parse_blocks(header: list[str], data: list[list[str]]) -> list[DayBlock]:
    """Split the data rows into per-day blocks anchored on banner rows.

    Columns are resolved leniently: any of these that exist in the live header
    get mapped; missing ones (e.g. Discipline, which Oona may delete) simply
    read back as empty. Only the columns the digest actually renders matter.
    """
    wanted = (
        config.COL_DATE, config.COL_START, config.COL_END, config.COL_LOCATION,
        config.COL_ITEM, config.COL_NOTES, config.COL_TYPE, config.COL_OWNER,
        config.COL_DRESS_CODE, *[h for h, _ in config.STAFF_FUNCTION_COLS],
    )
    cols = {}
    for name in wanted:
        try:
            cols[name] = _col_index(header, name)
        except KeyError:
            pass  # column not present in this revision of the sheet

    def cell(row: list[str], name: str) -> str:
        i = cols.get(name)
        if i is None:
            return ""
        return row[i].strip() if i < len(row) else ""

    blocks: list[DayBlock] = []
    current: DayBlock | None = None
    for row in data:
        first = (row[0].strip() if row else "")
        if _is_banner(first):
            d, weekday, label = _parse_banner(first)
            current = DayBlock(date=d, weekday=weekday, label=label, banner=first)
            blocks.append(current)
            continue
        if current is None:
            continue  # rows before the first banner (shouldn't happen)
        # Skip fully-empty rows.
        if not any(c.strip() for c in row):
            continue
        rec = {name: cell(row, name) for name in wanted}
        rec["_idx"] = len(current.rows)
        current.rows.append(rec)
    return blocks


def find_block(blocks: list[DayBlock], target: date) -> DayBlock | None:
    """Find the block for a given calendar date, matching on month+day."""
    for b in blocks:
        if b.date and (b.date.month, b.date.day) == (target.month, target.day):
            return b
    return None


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", re.IGNORECASE)


def parse_time(raw: str) -> int | None:
    """Parse '6:00 AM' to minutes since midnight. Returns None for blank/TBD.

    '(next day)' (or any time before 6 AM) is treated as after-midnight and
    pushed past 24h so it sorts to the END of its day rather than the start.
    """
    if not raw:
        return None
    m = _TIME_RE.search(raw)
    if not m:
        return None
    hour, minute, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == "p" and hour != 12:
        hour += 12
    if ap == "a" and hour == 12:
        hour = 0
    minutes = hour * 60 + minute
    if "next day" in raw.lower() or minutes < 6 * 60:
        minutes += 24 * 60
    return minutes


def fmt_time(minutes: int) -> str:
    """Format minutes-since-midnight back to 'h:mm AM/PM' (mod 24h)."""
    minutes %= 24 * 60
    hour, minute = divmod(minutes, 60)
    ap = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12}:{minute:02d} {ap}"


def fmt_span(start: int | None, end: int | None) -> str:
    """Render a 'h:mm AM – h:mm AM' span, gracefully handling missing pieces."""
    if start is None and end is None:
        return ""
    if end is None or end == start:
        return fmt_time(start)
    if start is None:
        return fmt_time(end)
    return f"{fmt_time(start)} – {fmt_time(end)}"


# --------------------------------------------------------------------------- #
# Section extraction
# --------------------------------------------------------------------------- #
def _type_matches(row: dict, type_value: str) -> bool:
    return row[config.COL_TYPE].strip().lower() == type_value.lower()


def rows_of_type(block: DayBlock, type_value: str) -> list[dict]:
    return [r for r in block.rows if _type_matches(r, type_value)]


def event_span(block: DayBlock) -> str:
    """Day span from the 'Top/End of Day' marker rows only (earliest -> latest)."""
    times: list[int] = []
    for r in rows_of_type(block, config.TYPE_SPAN_MARKER):
        for key in (config.COL_START, config.COL_END):
            t = parse_time(r[key])
            if t is not None:
                times.append(t)
    if not times:
        return ""
    return fmt_span(min(times), max(times))


def dress_code(block: DayBlock) -> str:
    """Distinct dress code(s) across the day's Show rows ('' if none)."""
    vals: list[str] = []
    for r in rows_of_type(block, config.TYPE_SHOW):
        v = r.get(config.COL_DRESS_CODE, "").strip()
        if v and v not in vals:
            vals.append(v)
    return " / ".join(vals)


def group_consecutive_shows(block: DayBlock) -> list[dict]:
    """Collapse runs of adjacent Show rows into grouped entries.

    Returns a list of {'span': str, 'items': [item names]} — one per contiguous
    run of Show rows (contiguity is judged by position within the day block).
    """
    shows = rows_of_type(block, config.TYPE_SHOW)
    groups: list[dict] = []
    run: list[dict] = []

    def flush():
        if not run:
            return
        start = parse_time(run[0][config.COL_START])
        # span end = last row's End if present, else its Start
        end = parse_time(run[-1][config.COL_END]) or parse_time(run[-1][config.COL_START])
        groups.append({
            "span": fmt_span(start, end),
            "items": [r[config.COL_ITEM] for r in run if r[config.COL_ITEM]],
        })

    prev_idx = None
    for r in shows:
        if prev_idx is not None and r["_idx"] != prev_idx + 1:
            flush()
            run = []
        run.append(r)
        prev_idx = r["_idx"]
    flush()
    return groups


# A name cell can hold several people and an on-call/remote qualifier, e.g.
# "Liam H, Danny M" · "Sean (On call)" · "Niko - On Call" · "Joe - Remote" ·
# "Benjamin. James" (a stray period instead of a comma — seen in the sheet).
_QUALIFIER_RE = re.compile(r"on[\s-]?call|remote|standby", re.IGNORECASE)
# Split multiple people on comma, semicolon, or a period that precedes a name.
_PEOPLE_SPLIT_RE = re.compile(r"[,;]|\.\s+(?=[A-Za-z])")


def _parse_staff_cell(raw: str) -> list[tuple[str, str]]:
    """Parse a staffing cell into [(name, qualifier)] pairs.

    qualifier is "" normally, else a normalised tag ("on call" / "remote" /
    "standby"). Surrounding parens/dashes around the qualifier are stripped from
    the name so "Sean (On call)" -> ("Sean", "on call").
    """
    out: list[tuple[str, str]] = []
    for part in _PEOPLE_SPLIT_RE.split(raw or ""):
        part = part.strip()
        if not part:
            continue
        m = _QUALIFIER_RE.search(part)
        qualifier = ""
        if m:
            qualifier = re.sub(r"[\s-]+", " ", m.group(0).lower())  # "On-Call" -> "on call"
            part = part[:m.start()] + part[m.end():]                # drop it from the name
        name = part.strip(" -–—().").strip()
        if name:
            out.append((name, qualifier))
    return out


def crew_call(block: DayBlock) -> list[dict]:
    """Per function/system, who is on it and their merged day-span.

    Scans every staffing column (config.STAFF_FUNCTION_COLS) across the day's
    rows. For each system, each person is collapsed to a SINGLE span — their
    first call to their last out — sorted by call time. On-call/remote people
    keep their real window and carry a qualifier tag.

    Shift staffing: if a person appears in any Shift-type row, their span is
    taken from those shift rows ALONE (their event-row tags don't extend it),
    so shift-staffed coverage reflects the shift window, not every event they
    happen to be tagged on.

    Returns [{'label', 'people': [{'name','span','qualifier'}]}] in column order,
    skipping systems with nobody on them.
    """
    out: list[dict] = []
    for header_name, label in config.STAFF_FUNCTION_COLS:
        agg: dict[str, dict] = {}  # name -> {times, shift_times, qualifier}
        for r in block.rows:
            cell = r.get(header_name, "")
            if not cell:
                continue
            bounds = [t for t in (parse_time(r[config.COL_START]),
                                  parse_time(r[config.COL_END])) if t is not None]
            is_shift = _type_matches(r, config.TYPE_SHIFT)
            for name, qualifier in _parse_staff_cell(cell):
                a = agg.setdefault(name, {"times": [], "shift_times": [], "qualifier": ""})
                a["times"].extend(bounds)
                if is_shift:
                    a["shift_times"].extend(bounds)
                if qualifier:
                    a["qualifier"] = qualifier
        people = []
        for name, a in agg.items():
            # A shift row, if present, defines the window; else merge all rows.
            times = a["shift_times"] or a["times"]
            people.append({
                "name": name,
                "span": fmt_span(min(times), max(times)) if times else "",
                "qualifier": a["qualifier"],
                "shift": bool(a["shift_times"]),   # staffed via a Shift row
                "_sort": min(times) if times else 24 * 60 * 10,
            })
        people.sort(key=lambda p: (p["_sort"], p["name"]))
        if people:
            out.append({"label": label, "people": people})
    return out
