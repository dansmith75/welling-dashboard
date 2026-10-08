#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

ALIASES = {"keiran-d": "kieran-d"}
DISPLAY_OVERRIDES = {"kieran-d": "Kieran"}


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return ALIASES.get(pid, pid)


def active_player_ids(core, book) -> list[str]:
    if "Squad" not in [s.name for s in book.sheets]:
        return []
    sheet = book.sheets["Squad"]
    try:
        table = core.find_table(sheet,"Squad",("ID","Display Name","Active"))
    except Exception:
        return []

    players: list[str] = []
    for row in core.table_dict_rows(table):
        pid = canonical_id(row.get("ID"))
        status = str(row.get("Status") or "").strip().lower()
        active = bool(row.get("Active")) and status != "left"
        if pid.lower() in ("total", "count"):
            continue
        if pid and active and pid not in players:
            players.append(pid)
    return players


def attendance_sessions(core, book, session_type):
    """Merge agreeing raw statuses, flag ambiguities instead of picking a winner."""
    table = core.find_table(book.sheets[core.ATTENDANCE_SHEET], core.ATTENDANCE_TABLE,
                           ("RecordKey", "SessionId", "SessionDate", "PlayerId", "Status", "Source"))
    grouped = {}
    for row in core.table_dict_rows(table):
        if str(row.get("SessionType") or "").strip().casefold() != session_type.casefold():
            continue
        day = core.iso_date(row.get("SessionDate"))
        venue = str(row.get("Venue") or "").strip().casefold()
        pid = canonical_id(row.get("PlayerId"))
        status = str(row.get("Status") or "").strip().casefold()
        if not day or not pid:
            continue
        session = grouped.setdefault((day, venue), {
            "SessionDate": day, "Venue": venue, "Players": {}, "Conflicts": set()})
        if pid in session["Players"] and session["Players"][pid] != status:
            session["Conflicts"].add(pid)
            core.flag_conflict("view_status_conflict", date=day, venue=venue, PlayerId=pid)
        else:
            session["Players"][pid] = status
    for session in grouped.values():
        for pid in session.pop("Conflicts"):
            session["Players"].pop(pid, None)
    return list(grouped.values())


def _present(value):
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().casefold() in ("true", "false"):
        return value.strip().casefold() == "true"
    return None


def refresh_preserving_history(core, book, session_type):
    """Fill blank cells and append new dates; never clear or overwrite history."""
    name = "Match Attendance" if session_type == "Match" else "Training Attendance"
    if name not in [s.name for s in book.sheets]:
        return 0
    sheet = book.sheets[name]
    values = sheet.used_range.value or []
    if not values or not isinstance(values[0], list):
        core.flag_conflict("view_layout_missing", sheet=name)
        return 0
    headers = values[0]
    players = {canonical_id(h): i + 1 for i, h in enumerate(headers)
               if i >= 3 and h and str(h).strip().casefold() not in ("count", "total")}
    count_cols = [i + 1 for i, h in enumerate(headers) if str(h or "").strip().casefold() in ("count", "total")]
    dates = {}
    for i, row in enumerate(values[1:], 2):
        day = core.iso_date(row[0] if row else None)
        if day:
            dates.setdefault(day, []).append(i)
    sessions = attendance_sessions(core, book, session_type)
    by_date = {}
    for session in sessions:
        by_date.setdefault(session["SessionDate"], []).append(session)
    fixtures = core.fixture_rows(book) if session_type == "Match" else []
    changed = 0
    for day, candidates in sorted(by_date.items()):
        if len(candidates) != 1 or len(dates.get(day, [])) > 1:
            core.flag_conflict("ambiguous_view_date", sheet=name, date=day)
            continue
        session = candidates[0]
        statuses = session["Players"]
        if not statuses:
            continue
        unknown = sorted(set(statuses) - set(players))
        if unknown:
            core.flag_conflict("view_missing_player_columns", sheet=name, date=day, players=unknown)
        row_numbers = dates.get(day, [])
        if not row_numbers:
            label = "Training"
            if session_type == "Match":
                matches = [f for f in fixtures if core.iso_date(f.get("Date")) == day]
                if len(matches) != 1:
                    core.flag_conflict("view_fixture_ambiguous_or_missing", date=day)
                    continue
                label = matches[0].get("Opposition") or ""
            row_number = max(sheet.used_range.last_cell.row, 1) + 1
            new_row = [None] * len(headers)
            new_row[:3] = [core.excel_date(day), core.excel_date(day), label]
            for pid, col in players.items():
                if pid in statuses:
                    new_row[col - 1] = statuses[pid] in ("present", "late")
            for col in count_cols:
                new_row[col - 1] = sum(v is True for v in new_row[3:])
            sheet.range((row_number, 1), (row_number, len(headers))).value = [new_row]
            sheet.range((row_number, 1)).number_format = "dd-mm-yy"
            sheet.range((row_number, 2)).number_format = "dddd"
            # Extend an existing display table only when it covers this view.
            for table in sheet.tables:
                if table.range.row == 1 and table.range.column == 1:
                    table.resize(sheet.range((1, 1), (row_number, table.range.columns.count)))
            dates[day] = [row_number]
            changed += 1
            continue
        row_number = row_numbers[0]
        row_changed = False
        for pid, col in players.items():
            if pid not in statuses:
                continue
            expected = statuses[pid] in ("present", "late")
            cell = sheet.range((row_number, col))
            current = cell.value
            formula = cell.formula
            if current in (None, "") and not (isinstance(formula, str) and formula.startswith("=")):
                cell.value = expected
                row_changed = True
            elif _present(current) != expected:
                core.flag_conflict("view_existing_value_conflict", sheet=name, date=day,
                                   PlayerId=pid, existing=current, incoming=expected)
        if row_changed:
            for col in count_cols:
                cell = sheet.range((row_number, col))
                formula = cell.formula
                if cell.value in (None, "") and not (isinstance(formula, str) and formula.startswith("=")):
                    cell.value = sum(sheet.range((row_number, c)).value is True for c in players.values())
            changed += 1
    return changed


def refresh_match_attendance_sheet(core, book):
    return refresh_preserving_history(core, book, "Match")


def refresh_training_attendance_sheet(core, book):
    return refresh_preserving_history(core, book, "Training")


def install(core):
    core.active_player_ids = lambda book: active_player_ids(core, book)
    core.refresh_match_attendance_sheet = lambda book: refresh_match_attendance_sheet(core, book)
    core.refresh_training_attendance_sheet = lambda book: refresh_training_attendance_sheet(core, book)
    def refresh(book):
        result = {"matchRows": refresh_match_attendance_sheet(core, book),
                  "trainingRows": refresh_training_attendance_sheet(core, book)}
        core.write_conflict_report(book)
        return result
    core.refresh_wide_attendance_sheets = refresh
