#!/usr/bin/env python3
"""Lint — and safely auto-fix — the NGS production schedule so the digest parses.

This is the "formatting clean up" the collaborators run from the Sheet menu. It
uses the SAME parser as the digest (schedule_reader), so "valid here" means
"the digest will read it correctly".

Read-only by default. `--fix` applies only NON-LOSSY normalisations:
  * trim leading/trailing whitespace
  * rewrite a cell that is *purely* a time into canonical "h:mm AM/PM"
Anything that needs a human judgement call — unknown Type, End-before-Start, an
unparseable banner date, a missing column, a crew cell that won't parse — is
REPORTED, never silently changed.

`--report-to-sheet` writes the findings to a "Formatting Report" tab so a
collaborator sees results without leaving the sheet.

Usage:
    python sheet_lint.py                      # report to stdout (read-only)
    python sheet_lint.py --fix                # apply safe fixes too
    python sheet_lint.py --report-to-sheet    # also write the report tab
    python sheet_lint.py --fix --report-to-sheet
"""
from __future__ import annotations

import argparse
import difflib
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread

import config
import schedule_reader as sr

REPORT_TAB = "Formatting Report"
_KNOWN_TYPES_LC = {t.lower() for t in config.KNOWN_TYPES}
_KNOWN_LOCS_LC = {l.lower() for l in config.KNOWN_LOCATIONS}


def _pure_time_canon(raw: str) -> str | None:
    """If the cell is *only* a time (no extra words), return its canonical
    'h:mm AM/PM' form; otherwise None so we never overwrite richer text."""
    s = raw.strip()
    if not s or "next day" in s.lower():
        return None
    m = sr._TIME_RE.search(s)
    if not m or s[:m.start()].strip() or s[m.end():].strip():
        return None  # there's other text in the cell — leave it alone
    minutes = sr.parse_time(s)
    return sr.fmt_time(minutes) if minutes is not None else None


def lint(fix: bool) -> dict:
    """Scan the live Schedule tab. Returns a result dict with issues + fixes."""
    gc = sr._client()
    ws = gc.open_by_key(config.SHEET_KEY).worksheet(config.SCHEDULE_TAB)
    values = ws.get_all_values()
    h = sr._detect_header_row(values)
    header = values[h]
    norm = [c.strip().lower() for c in header]

    def col(name: str) -> int | None:
        try:
            return norm.index(name.strip().lower())
        except ValueError:
            return None

    issues: list[tuple[str, int | None, str]] = []   # (severity, sheet_row, message)
    edits: dict[str, str] = {}                        # A1 -> new value (deduped)

    # --- header completeness ---
    required = [config.COL_DATE, config.COL_START, config.COL_END,
                config.COL_ITEM, config.COL_TYPE, config.COL_LOCATION]
    for name in required:
        if col(name) is None:
            issues.append(("error", h + 1, f"required column '{name}' is missing from the header row"))
    staff_cols = [(lbl, col(hn)) for hn, lbl in config.STAFF_FUNCTION_COLS]

    ci_start, ci_end = col(config.COL_START), col(config.COL_END)
    ci_type, ci_loc = col(config.COL_TYPE), col(config.COL_LOCATION)

    prev_banner_date = None
    for r in range(h + 1, len(values)):
        row = values[r]
        rownum = r + 1  # 1-based sheet row

        # Safe fix on every cell: trim stray whitespace.
        for c, val in enumerate(row):
            if val and val != val.strip():
                edits[gspread.utils.rowcol_to_a1(rownum, c + 1)] = val.strip()

        first = row[0].strip() if row else ""
        if sr._is_banner(first):
            d, _weekday, _label = sr._parse_banner(first)
            if d is None:
                issues.append(("error", rownum, f"day banner date won't parse: {first!r}"))
            elif prev_banner_date and d < prev_banner_date:
                issues.append(("warn", rownum, f"day banner out of chronological order: {first!r}"))
            if d:
                prev_banner_date = d
            continue

        if not any(c.strip() for c in row):
            continue  # blank spacer row

        # --- times ---
        for ci, lab in ((ci_start, "Start"), (ci_end, "End")):
            if ci is None or ci >= len(row):
                continue
            raw = row[ci].strip()
            if not raw or raw.lower() == "tbd":
                continue
            if sr.parse_time(raw) is None:
                issues.append(("warn", rownum, f"{lab} time not recognised: {raw!r} (use e.g. '6:00 AM' or 'TBD')"))
            else:
                canon = _pure_time_canon(raw)
                if canon and canon != raw:
                    edits[gspread.utils.rowcol_to_a1(rownum, ci + 1)] = canon

        # --- End before Start ---
        if ci_start is not None and ci_end is not None and ci_start < len(row) and ci_end < len(row):
            st, en = sr.parse_time(row[ci_start]), sr.parse_time(row[ci_end])
            if st is not None and en is not None and en < st:
                issues.append(("warn", rownum, f"End ({sr.fmt_time(en)}) is before Start ({sr.fmt_time(st)})"))

        # --- Type ---
        # Only the "driver" types (config.KNOWN_TYPES) change how a row renders;
        # any other value (MOE Ops, Events, VIPs, …) is a fine ordinary event. So
        # we don't flag unknown types wholesale — we only flag a value that looks
        # like a *typo* of a driver type (e.g. "Suppot" -> "Support"), which would
        # silently strip a row's tint/dot or fail to hide a Shift row.
        if ci_type is not None and ci_type < len(row):
            tv = row[ci_type].strip()
            if tv and tv.lower() not in _KNOWN_TYPES_LC:
                near = difflib.get_close_matches(tv.lower(), _KNOWN_TYPES_LC, n=1, cutoff=0.8)
                if near:
                    canonical = next(t for t in config.KNOWN_TYPES if t.lower() == near[0])
                    issues.append(("warn", rownum, f"Type {tv!r} looks like a typo of {canonical!r}"))

        # --- Location (only if a known set is configured) ---
        if _KNOWN_LOCS_LC and ci_loc is not None and ci_loc < len(row):
            lv = row[ci_loc].strip()
            if lv and lv.lower() not in _KNOWN_LOCS_LC:
                issues.append(("warn", rownum, f"Location not recognised: {lv!r}"))

        # --- crew cells: flag ones the parser can't read (report-only — never
        #     round-trip them, since reformatting could drop content) ---
        for lbl, ci in staff_cols:
            if ci is None or ci >= len(row):
                continue
            raw = row[ci].strip()
            if raw and not sr._parse_staff_cell(raw):
                issues.append(("warn", rownum, f"{lbl} crew cell didn't parse: {raw!r}"))

    applied = 0
    if fix and edits:
        ws.batch_update([{"range": a1, "values": [[v]]} for a1, v in edits.items()])
        applied = len(edits)

    return {
        "worksheet": ws,
        "spreadsheet": ws.spreadsheet,
        "issues": issues,
        "edits": edits,
        "applied": applied,
        "errors": sum(1 for s, _, _ in issues if s == "error"),
        "warnings": sum(1 for s, _, _ in issues if s == "warn"),
    }


def _format_report(res: dict, fix: bool) -> list[str]:
    lines = []
    if fix:
        lines.append(f"Auto-fixed {res['applied']} cell(s) (whitespace / time format).")
    elif res["edits"]:
        lines.append(f"{len(res['edits'])} cell(s) could be auto-fixed — re-run with --fix to apply.")
    lines.append(f"{res['errors']} error(s), {res['warnings']} warning(s) needing a human:")
    if not res["issues"]:
        lines.append("  none — the sheet is clean. ✅")
    for sev, rownum, msg in res["issues"]:
        where = f"row {rownum}" if rownum else "header"
        lines.append(f"  [{sev.upper()}] {where}: {msg}")
    return lines


def write_report_tab(res: dict, fix: bool) -> None:
    sh = res["spreadsheet"]
    try:
        rep = sh.worksheet(REPORT_TAB)
        rep.clear()
    except gspread.WorksheetNotFound:
        rep = sh.add_worksheet(title=REPORT_TAB, rows=200, cols=3)

    stamp = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %I:%M %p %Z")
    rows = [[f"NGS schedule formatting check — {stamp}"], [""]]
    if fix:
        rows.append([f"Auto-fixed {res['applied']} cell(s) (whitespace / time format)."])
    rows.append([f"{res['errors']} error(s), {res['warnings']} warning(s) needing a human:"])
    if not res["issues"]:
        rows.append(["none — the sheet is clean."])
    for sev, rownum, msg in res["issues"]:
        where = f"row {rownum}" if rownum else "header"
        rows.append([sev.upper(), where, msg])
    rep.update(range_name="A1", values=rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint and safely auto-fix the NGS schedule sheet.")
    ap.add_argument("--fix", action="store_true", help="apply safe fixes (whitespace, time format)")
    ap.add_argument("--report-to-sheet", action="store_true",
                    help=f"write findings to the '{REPORT_TAB}' tab")
    args = ap.parse_args()

    res = lint(fix=args.fix)
    report = _format_report(res, args.fix)
    print("\n".join(report))
    if args.report_to_sheet:
        write_report_tab(res, args.fix)
        print(f"\nWrote report to the '{REPORT_TAB}' tab.")
    # Exit non-zero only on hard errors (missing columns / unparseable banners),
    # so a scheduled lint can surface real breakage while warnings stay advisory.
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
