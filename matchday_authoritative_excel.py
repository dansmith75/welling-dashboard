#!/usr/bin/env python3
"""Authoritative completed-Matchday reconciliation into the Excel workbook.

For completed fixtures, Supabase Matchday is the source of truth. MatchdayRecords
is rebuilt from the latest completed sessions and the Goals/Assists/Events/
Fixtures summary rows for those fixtures are overwritten from the Matchday
payload rather than incremented. This makes later corrections idempotent.
"""
from __future__ import annotations

from typing import Any

import sync_supabase_to_excel as core


def normal(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def latest_completed_sessions() -> list[dict[str, Any]]:
    rows = core.api_get(
        "matchday_sessions",
        "id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload",
        "finished_at.asc",
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not (row.get("finished_at") or payload.get("finishedAt")):
            continue
        fixture = payload.get("fixture") or {}
        key = str(payload.get("matchId") or row.get("match_id") or f"{fixture.get('date') or row.get('match_date')}|{fixture.get('opposition') or row.get('opposition')}")
        latest[key] = row
    return list(latest.values())


def table_headers(table) -> list[str]:
    return core.table_headers(table)


def rebuild_matchday_records(book, sessions: list[dict[str, Any]]) -> int:
    sheet, table = core.ensure_matchday_table(book)
    headers = table_headers(table)
    rows: list[dict[str, Any]] = []
    for session in sessions:
        rows.extend(core.matchday_rows(session))

    start_row = table.range.row
    start_col = table.range.column
    old_rows = max(table.range.rows.count, 2)
    old_cols = max(table.range.columns.count, len(headers))
    sheet.range((start_row + 1, start_col), (start_row + old_rows - 1, start_col + old_cols - 1)).clear_contents()

    end_rows = max(len(rows) + 1, 2)
    table.resize(sheet.range((start_row, start_col), (start_row + end_rows - 1, start_col + len(headers) - 1)))
    if rows:
        matrix = [[row.get(header, "") for header in headers] for row in rows]
        sheet.range((start_row + 1, start_col), (start_row + len(rows), start_col + len(headers) - 1)).value = matrix
    else:
        sheet.range((start_row + 1, start_col), (start_row + 1, start_col + len(headers) - 1)).clear_contents()
    return len(rows)


def find_header_column(sheet, *names: str) -> int | None:
    headers = sheet.range((1, 1), (1, sheet.used_range.last_cell.column)).value
    if not isinstance(headers, list):
        headers = [headers]
    wanted = {normal(name) for name in names}
    for idx, header in enumerate(headers, start=1):
        if normal(header) in wanted:
            return idx
    return None


def overwrite_wide_stats(book, session: dict[str, Any]) -> list[str]:
    payload = session.get("payload") or {}
    fixture = payload.get("fixture") or {}
    match_date = fixture.get("date") or session.get("match_date") or ""
    opposition = fixture.get("opposition") or session.get("opposition") or ""
    names = core.player_lookup(payload)
    for stat in payload.get("playerStats") or []:
        pid = str(stat.get("playerId") or "")
        if pid and stat.get("displayName"):
            names[pid] = str(stat.get("displayName"))

    goal_counts: dict[str, int] = {}
    assist_counts: dict[str, int] = {}
    event_text: dict[str, str] = {}
    goals_for = 0
    goals_against = 0

    for event in payload.get("events") or []:
        etype = str(event.get("type") or "")
        pid = str(event.get("playerId") or "")
        if etype in ("Goal", "Own Goal"):
            goals_for += 1
        elif etype == "Opponent Goal":
            goals_against += 1

        if etype == "Goal" and pid:
            display = names.get(pid, pid)
            goal_counts[display] = goal_counts.get(display, 0) + 1
            assist_id = str(event.get("assistPlayerId") or "")
            if assist_id:
                assist_name = names.get(assist_id, assist_id)
                assist_counts[assist_name] = assist_counts.get(assist_name, 0) + 1
        elif etype in ("Card", "Note") and pid:
            display = names.get(pid, pid)
            minute = event.get("minute")
            prefix = f"{minute}' " if minute not in (None, "") else ""
            detail = event.get("cardType") if etype == "Card" else event.get("text")
            text = f"{prefix}{detail or etype}"
            event_text[display] = f"{event_text[display]} | {text}" if display in event_text else text

    warnings: list[str] = []
    payloads = {"Goals": goal_counts, "Assists": assist_counts, "Events": event_text}
    for sheet_name, values in payloads.items():
        if sheet_name not in [s.name for s in book.sheets]:
            warnings.append(f"Missing sheet: {sheet_name}")
            continue
        sheet = book.sheets[sheet_name]
        row = core.excel_row_for_match(sheet, match_date, opposition)
        if row is None:
            warnings.append(f"No {sheet_name} row for {match_date} v {opposition}")
            continue

        headers = sheet.range((1, 1), (1, sheet.used_range.last_cell.column)).value
        if not isinstance(headers, list):
            headers = [headers]
        for col, header in enumerate(headers, start=1):
            if normal(header) in {"date", "opposition", "count"}:
                continue
            if str(header or "").strip():
                sheet.range((row, col)).clear_contents()

        for display, value in values.items():
            col = core.player_column(sheet, display)
            if col:
                sheet.range((row, col)).value = value
            else:
                warnings.append(f"Could not place {sheet_name[:-1].lower()}: {display} v {opposition}")

    if "Fixtures" in [s.name for s in book.sheets]:
        sheet = book.sheets["Fixtures"]
        row = core.excel_row_for_match(sheet, match_date, opposition)
        if row is not None:
            gf_col = find_header_column(sheet, "Goals For", "GoalsFor", "GF")
            ga_col = find_header_column(sheet, "Goals Against", "GoalsAgainst", "GA")
            result_col = find_header_column(sheet, "Result")
            if gf_col:
                sheet.range((row, gf_col)).value = goals_for
            if ga_col:
                sheet.range((row, ga_col)).value = goals_against
            if result_col:
                sheet.range((row, result_col)).value = "W" if goals_for > goals_against else "L" if goals_for < goals_against else "D"
        else:
            warnings.append(f"No Fixtures row for {match_date} v {opposition}")

    return warnings


def import_matchday_authoritative(book) -> tuple[int, int, list[str]]:
    sessions = latest_completed_sessions()
    warnings: list[str] = []
    for session in sessions:
        warnings.extend(overwrite_wide_stats(book, session))
    row_count = rebuild_matchday_records(book, sessions)
    return len(sessions), row_count, warnings
