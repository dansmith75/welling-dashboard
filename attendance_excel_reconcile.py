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
        table = sheet.tables["Squad"]
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


def attendance_sessions(core, book, session_type: str) -> list[dict[str, Any]]:
    if core.ATTENDANCE_SHEET not in [s.name for s in book.sheets]:
        return []
    sheet = book.sheets[core.ATTENDANCE_SHEET]
    table = sheet.tables[core.ATTENDANCE_TABLE]
    rows = core.table_dict_rows(table)

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("SessionType") or "").strip().lower() != session_type.lower():
            continue
        key = str(row.get("SessionKey") or "").strip()
        if not key:
            continue
        submitted_at = str(row.get("SubmittedAt") or "")
        session = grouped.setdefault(key, {
            "SessionKey": key,
            "SessionDate": row.get("SessionDate"),
            "Venue": str(row.get("Venue") or "").strip(),
            "SubmittedAt": submitted_at,
            "Players": {},
        })
        if submitted_at > str(session.get("SubmittedAt") or ""):
            session["SubmittedAt"] = submitted_at
        pid = canonical_id(row.get("PlayerId"))
        if pid:
            session["Players"][pid] = str(row.get("Status") or "").strip()

    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for session in grouped.values():
        date_key = core.iso_date(session.get("SessionDate"))
        venue_key = str(session.get("Venue") or "").strip().lower()
        lookup_key = (date_key, venue_key)
        current = latest.get(lookup_key)
        if current is None or str(session.get("SubmittedAt") or "") >= str(current.get("SubmittedAt") or ""):
            latest[lookup_key] = session

    return sorted(latest.values(), key=lambda s: (core.iso_date(s.get("SessionDate")), str(s.get("Venue") or "")))


def matchday_presence(core) -> dict[str, set[str]]:
    presence: dict[str, set[str]] = {}
    sessions = core.api_get(
        "matchday_sessions",
        "id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload",
        "finished_at.asc",
    )
    for session in sessions:
        if not session.get("finished_at"):
            continue
        payload = session.get("payload") or {}
        fixture = payload.get("fixture") or {}
        date_key = core.iso_date(fixture.get("date") or session.get("match_date"))
        if not date_key:
            continue
        played = presence.setdefault(date_key, set())
        for stat in payload.get("playerStats") or []:
            try:
                minutes = float(stat.get("minutesPlayed") or 0)
            except Exception:
                minutes = 0
            pid = canonical_id(stat.get("playerId"))
            if pid and minutes > 0:
                played.add(pid)
    return presence


def _write_matrix(sheet, table_name: str, matrix: list[list[Any]], count_col: int) -> None:
    headers = matrix[0]
    old_last_row = max(sheet.used_range.last_cell.row, 2)
    old_last_col = max(sheet.used_range.last_cell.column, len(headers))
    sheet.range((1, 1), (old_last_row, old_last_col)).clear_contents()
    sheet.range("A1").value = matrix

    try:
        table = sheet.tables[table_name]
        table.resize(sheet.range((1, 1), (max(len(matrix), 2), len(headers))))
    except Exception:
        # These two display sheets are ordinary ranges in the master workbook.
        # Do not turn them into tables: Excel can revive deleted calculated
        # columns (notably the old Total column) when a ListObject is created.
        pass

    # Excel tables may try to reapply an old calculated-column formula after a resize.
    # Rewrite the data, then explicitly restore the final calculated Count column.
    sheet.range("A1").value = matrix
    if len(matrix) == 1:
        sheet.range((2, 1), (2, len(headers))).clear_contents()

    if len(matrix) > 1:
        # Player attendance starts in column D and Count is always the last column.
        # R1C1 keeps the formula correct when players are added or removed.
        sheet.range((2, count_col), (len(matrix), count_col)).api.FormulaR1C1 = "=COUNTIF(RC4:RC[-1],TRUE)"

    sheet.range("A:A").number_format = "dd-mm-yy"
    sheet.range("B:B").number_format = "dddd"


def refresh_match_attendance_sheet(core, book) -> int:
    sheet_name = "Match Attendance"
    table_name = "Match_Attendance"
    if sheet_name not in [s.name for s in book.sheets]:
        return 0

    sheet = book.sheets[sheet_name]
    players = active_player_ids(core, book)
    fixtures = core.fixture_rows(book)
    sessions = attendance_sessions(core, book, "Match")
    presence = matchday_presence(core)

    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for session in sessions:
        date_key = core.iso_date(session.get("SessionDate"))
        venue_key = str(session.get("Venue") or "").strip().lower()
        lookup[(date_key, venue_key)] = session
        lookup[(date_key, "")] = session

    headers = ["Date", "Day", "Opposition", *players, "COUNT"]
    matrix: list[list[Any]] = [headers]
    for fixture in fixtures:
        match_date = fixture.get("Date")
        date_key = core.iso_date(match_date)
        venue_key = str(fixture.get("HomeAway") or "").strip().lower()
        session = lookup.get((date_key, venue_key)) or lookup.get((date_key, ""))
        statuses = (session or {}).get("Players") or {}
        matchday_players = presence.get(date_key, set())
        present = [
            (canonical_id(pid) in matchday_players) or str(statuses.get(canonical_id(pid)) or "").lower() in ("present", "late")
            for pid in players
        ]
        matrix.append([
            core.excel_date(match_date),
            core.excel_date(match_date),
            str(fixture.get("Opposition") or ""),
            *present,
            sum(1 for value in present if value),
        ])

    _write_matrix(sheet, table_name, matrix, len(headers))
    return len(fixtures)


def _existing_training_dates(core, sheet) -> list[Any]:
    values = sheet.used_range.value
    if not values:
        return []
    if not isinstance(values[0], list):
        values = [values]
    dates: list[Any] = []
    for row in values[1:]:
        if not row:
            continue
        date_value = row[0] if len(row) else None
        if core.iso_date(date_value):
            dates.append(date_value)
    return dates


def _existing_training_statuses(core, sheet) -> dict[str, dict[str, bool]]:
    """Retain manually entered rows that do not yet exist in AttendanceRecords."""
    values = sheet.used_range.value
    if not values:
        return {}
    if not isinstance(values[0], list):
        values = [values]
    headers = [canonical_id(value) for value in values[0]]
    result: dict[str, dict[str, bool]] = {}
    for row in values[1:]:
        if not row:
            continue
        date_key = core.iso_date(row[0] if len(row) else None)
        if not date_key:
            continue
        statuses: dict[str, bool] = {}
        for index in range(3, min(len(row), len(headers))):
            player_id = headers[index]
            if player_id and player_id.lower() not in ("count", "total"):
                statuses[player_id] = bool(row[index])
        result[date_key] = statuses
    return result


def _promote_manual_training_rows(core, book, sheet) -> int:
    """Copy completed manual wide-sheet rows into the authoritative raw table."""
    existing_dates = {
        core.iso_date(session.get("SessionDate"))
        for session in attendance_sessions(core, book, "Training")
    }
    manual = _existing_training_statuses(core, sheet)
    raw_sheet = book.sheets[core.ATTENDANCE_SHEET]
    raw_table = raw_sheet.tables[core.ATTENDANCE_TABLE]
    new_rows: list[dict[str, Any]] = []
    for date_key, statuses in manual.items():
        if date_key in existing_dates or not any(statuses.values()):
            continue
        session_key = f"{date_key}-training-na-manual"
        for player_id, present in statuses.items():
            new_rows.append({
                "RecordKey": f"{session_key}-{player_id}",
                "SessionKey": session_key,
                "SessionId": session_key,
                "SessionDate": date_key,
                "SessionType": "Training",
                "Venue": "",
                "PlayerId": player_id,
                "DisplayName": DISPLAY_OVERRIDES.get(player_id, player_id),
                "Status": "Present" if present else "Absent",
                "FeePaid": "",
                "PaymentStatus": "",
                "LatePayment": "",
                "SubmittedBy": "Dan",
                "SubmittedAt": "",
                "Source": "Excel",
            })
    return core.append_table_rows(raw_sheet, raw_table, new_rows)


def refresh_training_attendance_sheet(core, book) -> int:
    sheet_name = "Training Attendance"
    table_name = "Training_Attendance"
    if sheet_name not in [s.name for s in book.sheets]:
        return 0

    sheet = book.sheets[sheet_name]
    players = active_player_ids(core, book)
    _promote_manual_training_rows(core, book, sheet)
    sessions = attendance_sessions(core, book, "Training")
    by_date = {core.iso_date(s.get("SessionDate")): s for s in sessions}
    existing_statuses = _existing_training_statuses(core, sheet)

    # Preserve the workbook's scheduled training-date rows, then add any submitted
    # sessions that are not already represented. This avoids turning the sheet into
    # an apparently empty table between sessions.
    dates = _existing_training_dates(core, sheet)
    seen = {core.iso_date(d) for d in dates}
    for session in sessions:
        key = core.iso_date(session.get("SessionDate"))
        if key and key not in seen:
            dates.append(session.get("SessionDate"))
            seen.add(key)
    dates.sort(key=core.iso_date)

    # Safety: never destructively replace a populated sheet with only a header
    # because a transient source read returned no sessions/dates.
    if not dates and sheet.used_range.last_cell.row > 1:
        return 0

    headers = ["Date", "Day", "Session", *players, "Count"]
    matrix: list[list[Any]] = [headers]
    for session_date in dates:
        session = by_date.get(core.iso_date(session_date))
        if session:
            statuses = session.get("Players") or {}
            present = [str(statuses.get(canonical_id(pid)) or "").lower() in ("present", "late") for pid in players]
        else:
            # A coach may add an older training row directly to this view before
            # it exists in the app's raw AttendanceRecords table.
            saved = existing_statuses.get(core.iso_date(session_date), {})
            present = [bool(saved.get(canonical_id(pid), False)) for pid in players]
        matrix.append([
            core.excel_date(session_date),
            core.excel_date(session_date),
            "Training",
            *present,
            sum(1 for value in present if value),
        ])

    _write_matrix(sheet, table_name, matrix, len(headers))
    return len(dates)


def install(core) -> None:
    core.active_player_ids = lambda book: active_player_ids(core, book)
    core.refresh_match_attendance_sheet = lambda book: refresh_match_attendance_sheet(core, book)
    core.refresh_training_attendance_sheet = lambda book: refresh_training_attendance_sheet(core, book)
    core.refresh_wide_attendance_sheets = lambda book: {
        "matchRows": refresh_match_attendance_sheet(core, book),
        "trainingRows": refresh_training_attendance_sheet(core, book),
    }
