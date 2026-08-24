#!/usr/bin/env python3
"""Authoritative completed-Matchday reconciliation into the Excel workbook.

For completed fixtures, Supabase Matchday is the source of truth. MatchdayRecords
is rebuilt from the latest completed sessions and the Fixtures / Goals / Assists /
Events summary rows for those fixtures are overwritten from the Matchday payload
rather than incremented. This makes later corrections idempotent.

Goals/Assists Total columns are retained as Excel audit totals, but are derived
from the player columns and are never treated as a source of truth.
"""
from __future__ import annotations

from typing import Any

import sync_supabase_to_excel as core


def normal(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return "kieran-d" if pid == "keiran-d" else pid


def canonical_name(pid: Any, value: Any) -> str:
    if canonical_id(pid) == "kieran-d":
        return "Kieran"
    return str(value or canonical_id(pid) or "").strip()


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


def squad_display_names(book) -> set[str]:
    names: set[str] = set()
    if "Squad" not in [s.name for s in book.sheets]:
        return names
    try:
        table = book.sheets["Squad"].tables["Squad"]
    except Exception:
        return names
    for row in core.table_dict_rows(table):
        pid = canonical_id(row.get("ID"))
        name = canonical_name(pid, row.get("Display Name") or row.get("Name"))
        if name:
            names.add(name)
    return names


def set_total_formula(book, sheet, row: int) -> None:
    """Refresh a Total column, if present, from player columns only."""
    total_col = find_header_column(sheet, "Total")
    if not total_col:
        return

    player_names = squad_display_names(book)
    headers = sheet.range((1, 1), (1, sheet.used_range.last_cell.column)).value
    if not isinstance(headers, list):
        headers = [headers]

    player_cols = [idx for idx, header in enumerate(headers, start=1) if str(header or "").strip() in player_names]
    if not player_cols:
        sheet.range((row, total_col)).value = 0
        return

    refs = [sheet.range((row, col)).address for col in player_cols]
    sheet.range((row, total_col)).formula = f"=SUM({','.join(refs)})"


def names_for_payload(payload: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for player in payload.get("squad") or []:
        pid = canonical_id(player.get("playerId"))
        if pid:
            names[pid] = canonical_name(pid, player.get("displayName"))
    for stat in payload.get("playerStats") or []:
        pid = canonical_id(stat.get("playerId"))
        if pid:
            names[pid] = canonical_name(pid, stat.get("displayName"))
    return names


def overwrite_wide_stats(book, session: dict[str, Any]) -> list[str]:
    payload = session.get("payload") or {}
    fixture = payload.get("fixture") or {}
    match_date = fixture.get("date") or session.get("match_date") or ""
    opposition = fixture.get("opposition") or session.get("opposition") or ""
    names = names_for_payload(payload)

    goal_counts: dict[str, int] = {}
    assist_counts: dict[str, int] = {}
    event_text: dict[str, str] = {}
    goals_for = 0
    goals_against = 0

    for event in payload.get("events") or []:
        etype = str(event.get("type") or "")
        pid = canonical_id(event.get("playerId"))
        if etype in ("Goal", "Own Goal"):
            goals_for += 1
        elif etype == "Opponent Goal":
            goals_against += 1

        if etype == "Goal" and pid:
            display = names.get(pid, canonical_name(pid, pid))
            goal_counts[display] = goal_counts.get(display, 0) + 1
            assist_id = canonical_id(event.get("assistPlayerId"))
            if assist_id:
                assist_name = names.get(assist_id, canonical_name(assist_id, assist_id))
                assist_counts[assist_name] = assist_counts.get(assist_name, 0) + 1
        elif etype in ("Card", "Note") and pid:
            display = names.get(pid, canonical_name(pid, pid))
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
            # Metadata and audit totals are preserved/recalculated rather than blanked.
            if normal(header) in {"date", "opposition", "count", "total"}:
                continue
            if str(header or "").strip():
                sheet.range((row, col)).clear_contents()

        for display, value in values.items():
            col = core.player_column(sheet, display)
            if col:
                sheet.range((row, col)).value = value
            else:
                warnings.append(f"Could not place {sheet_name[:-1].lower()}: {display} v {opposition}")

        if sheet_name in ("Goals", "Assists"):
            set_total_formula(book, sheet, row)

    if "Fixtures" in [s.name for s in book.sheets]:
        sheet = book.sheets["Fixtures"]
        row = core.excel_row_for_match(sheet, match_date, opposition)
        if row is not None:
            gf_col = find_header_column(sheet, "Goals For", "GoalsFor", "GF")
            ga_col = find_header_column(sheet, "Goals Against", "GoalsAgainst", "GA")
            result_col = find_header_column(sheet, "Result")
            if gf_col:
                sheet.range((row, gf_col)).value = goals_for
            else:
                warnings.append("Fixtures sheet has no Goals For / GF column")
            if ga_col:
                sheet.range((row, ga_col)).value = goals_against
            else:
                warnings.append("Fixtures sheet has no Goals Against / GA column")
            if result_col:
                sheet.range((row, result_col)).value = "W" if goals_for > goals_against else "L" if goals_for < goals_against else "D"
        else:
            warnings.append(f"No Fixtures row for {match_date} v {opposition}")
    else:
        warnings.append("Missing sheet: Fixtures")

    return warnings


def import_matchday_authoritative(book) -> tuple[int, int, list[str]]:
    sessions = latest_completed_sessions()
    warnings: list[str] = []
    for session in sessions:
        warnings.extend(overwrite_wide_stats(book, session))
    row_count = rebuild_matchday_records(book, sessions)
    return len(sessions), row_count, warnings
