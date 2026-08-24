#!/usr/bin/env python3
"""Pull centrally submitted Attendance/Matchday data from Supabase into Excel.

Excel remains the football-data source of truth. This script uses xlwings so
Excel itself opens/saves the workbook rather than rewriting the XLSX package.
That keeps the existing workbook structure, tables and formulas under Excel's
control on Windows and macOS.

The Supabase key below is the app's public publishable/anon key, not a secret.
The database must allow anon SELECT on attendance_sessions,
attendance_records and matchday_sessions.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

SUPABASE_URL = "https://dszgeoimkilzeeqapish.supabase.co"
SUPABASE_KEY = "sb_publishable_uTJVDSSD7jPePv1BdODmSg_qO6U8get"

ATTENDANCE_SHEET = "AttendanceRecords"
ATTENDANCE_TABLE = "AttendanceRecords"
MATCHDAY_SHEET = "MatchdayRecords"
MATCHDAY_TABLE = "MatchdayRecords"

MATCHDAY_HEADERS = [
    "ImportKey","SessionId","MatchId","MatchDate","Opposition","Competition",
    "RecordType","PlayerId","DisplayName","RelatedPlayerId","RelatedDisplayName",
    "Minute","Detail","Value","SubmittedBy","StartedAt","FinishedAt","Source",
]


def api_get(table: str, select: str, order: str | None = None) -> list[dict[str, Any]]:
    params = {"select": select}
    if order:
        params["order"] = order
    url = f"{SUPABASE_URL}/rest/v1/{table}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"Could not read Supabase table '{table}'. Check internet access and the anon SELECT policy."
        ) from exc


def iso_date(value: Any) -> str:
    """Return YYYY-MM-DD for Excel/Python/string date values.

    xlwings can return an Excel date either as datetime or as the raw serial
    number depending on workbook/table state. Supporting both prevents completed
    Matchday rows from failing to match existing Fixtures/Goals/Assists/Events.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            # Excel's 1900 date system, including its historic leap-year offset.
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
        except Exception:
            pass
    text = str(value).strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return text[:10]


def excel_date(value: Any) -> datetime | str:
    text = iso_date(value)
    if not text:
        return ""
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return text


def table_headers(table) -> list[str]:
    values = table.range.rows[0].value
    if not isinstance(values, list):
        values = [values]
    return [str(v or "").strip() for v in values]


def table_existing_column_values(table, header: str) -> set[str]:
    headers = table_headers(table)
    if header not in headers:
        return set()
    idx = headers.index(header) + 1
    values = table.range.columns[idx - 1].value
    if not isinstance(values, list):
        values = [values]
    return {str(v) for v in values[1:] if v not in (None, "")}


def table_dict_rows(table) -> list[dict[str, Any]]:
    values = table.range.value
    if not values:
        return []
    if not isinstance(values[0], list):
        values = [values]
    headers = [str(v or "").strip() for v in values[0]]
    rows: list[dict[str, Any]] = []
    for raw in values[1:]:
        if not raw or all(v in (None, "") for v in raw):
            continue
        rows.append({headers[i]: raw[i] if i < len(raw) else "" for i in range(len(headers))})
    return rows


def append_table_rows(sheet, table, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    headers = table_headers(table)
    start_row = table.range.row
    start_col = table.range.column
    current_rows = table.range.rows.count
    next_row = start_row + current_rows
    matrix = [[row.get(header, "") for header in headers] for row in rows]
    end_row = next_row + len(matrix) - 1
    end_col = start_col + len(headers) - 1
    sheet.range((next_row, start_col), (end_row, end_col)).value = matrix
    table.resize(sheet.range((start_row, start_col), (end_row, end_col)))
    return len(matrix)


def make_session_key(session: dict[str, Any]) -> str:
    date_part = session.get("session_date") or "unknown-date"
    type_part = str(session.get("session_type") or "session").lower()
    venue_part = str(session.get("venue") or "na").lower()
    return f"{date_part}-{type_part}-{venue_part}-{str(session.get('id'))[:8]}"


def import_attendance(book) -> int:
    sessions = api_get("attendance_sessions","id,session_date,session_type,venue,submitted_by,submitted_at","submitted_at.asc")
    records = api_get("attendance_records","session_id,player_id,display_name,status")
    if ATTENDANCE_SHEET not in [s.name for s in book.sheets]:
        raise RuntimeError(f"Workbook sheet '{ATTENDANCE_SHEET}' was not found.")
    sheet = book.sheets[ATTENDANCE_SHEET]
    try:
        table = sheet.tables[ATTENDANCE_TABLE]
    except Exception as exc:
        raise RuntimeError(f"Excel table '{ATTENDANCE_TABLE}' was not found.") from exc
    existing = table_existing_column_values(table, "RecordKey")
    sessions_by_id = {str(s["id"]): s for s in sessions}
    new_rows: list[dict[str, Any]] = []
    for record in records:
        session = sessions_by_id.get(str(record.get("session_id")))
        if not session:
            continue
        session_key = make_session_key(session)
        record_key = f"{session_key}-{record.get('player_id')}"
        if record_key in existing:
            continue
        new_rows.append({
            "RecordKey": record_key,"SessionKey": session_key,"SessionId": session.get("id"),
            "SessionDate": session.get("session_date"),"SessionType": session.get("session_type"),
            "Venue": session.get("venue") or "","PlayerId": record.get("player_id"),
            "DisplayName": record.get("display_name"),"Status": record.get("status"),
            "FeePaid": "","PaymentStatus": "","LatePayment": "",
            "SubmittedBy": session.get("submitted_by") or "","SubmittedAt": session.get("submitted_at") or "",
            "Source": "App",
        })
        existing.add(record_key)
    return append_table_rows(sheet, table, new_rows)


def active_player_ids(book) -> list[str]:
    if "Squad" not in [s.name for s in book.sheets]:
        return []
    sheet = book.sheets["Squad"]
    try:
        table = sheet.tables["Squad"]
    except Exception:
        return []
    players: list[str] = []
    for row in table_dict_rows(table):
        pid = str(row.get("ID") or "").strip()
        status = str(row.get("Status") or "").strip().lower()
        active = row.get("Active")
        is_active = bool(active) if isinstance(active, bool) else str(active or "").strip().lower() in {"true","yes","y","1"}
        if pid and (is_active or status == "active"):
            players.append(pid)
    return players


def fixture_rows(book) -> list[dict[str, Any]]:
    if "Fixtures" not in [s.name for s in book.sheets]:
        return []
    sheet = book.sheets["Fixtures"]
    try:
        table = sheet.tables["Fixtures"]
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for row in table_dict_rows(table):
        match_date = row.get("Date")
        opposition = str(row.get("Opposition") or "").strip()
        home_away = str(row.get("Home / Away") or "").strip()
        if iso_date(match_date) and opposition:
            rows.append({"Date": match_date,"Opposition": opposition,"HomeAway": home_away})
    return rows


def latest_attendance_sessions(book, session_type: str) -> list[dict[str, Any]]:
    sheet = book.sheets[ATTENDANCE_SHEET]
    table = sheet.tables[ATTENDANCE_TABLE]
    rows = table_dict_rows(table)
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("SessionType") or "").strip().lower() != session_type.lower():
            continue
        session_key = str(row.get("SessionKey") or "").strip()
        if not session_key:
            continue
        submitted_at = str(row.get("SubmittedAt") or "")
        session = grouped.setdefault(session_key, {"SessionKey":session_key,"SessionDate":row.get("SessionDate"),"Venue":str(row.get("Venue") or "").strip(),"SubmittedAt":submitted_at,"Players":{}})
        if submitted_at > str(session.get("SubmittedAt") or ""):
            session["SubmittedAt"] = submitted_at
        pid = str(row.get("PlayerId") or "").strip()
        if pid:
            session["Players"][pid] = str(row.get("Status") or "").strip()
    latest: dict[tuple[str,str],dict[str,Any]] = {}
    for session in grouped.values():
        key = (iso_date(session.get("SessionDate")), str(session.get("Venue") or "").lower())
        current = latest.get(key)
        if current is None or str(session.get("SubmittedAt") or "") >= str(current.get("SubmittedAt") or ""):
            latest[key] = session
    return sorted(latest.values(), key=lambda s:(iso_date(s.get("SessionDate")),str(s.get("Venue") or "")))


def attendance_session_lookup(book, session_type: str) -> dict[tuple[str,str],dict[str,Any]]:
    lookup = {}
    for session in latest_attendance_sessions(book, session_type):
        date_key = iso_date(session.get("SessionDate"))
        venue_key = str(session.get("Venue") or "").strip().lower()
        lookup[(date_key,venue_key)] = session
        lookup[(date_key,"")] = session
    return lookup


def refresh_match_attendance_sheet(book) -> int:
    sheet_name = "Match Attendance"
    table_name = "Match_Attendance"
    if sheet_name not in [s.name for s in book.sheets]: return 0
    sheet = book.sheets[sheet_name]
    players = active_player_ids(book)
    fixtures = fixture_rows(book)
    sessions = attendance_session_lookup(book,"Match")
    headers = ["Date","Day","Opposition",*players,"COUNT"]
    matrix = [headers]
    for fixture in fixtures:
        match_date = fixture.get("Date")
        date_key = iso_date(match_date)
        venue_key = str(fixture.get("HomeAway") or "").strip().lower()
        session = sessions.get((date_key,venue_key)) or sessions.get((date_key,""))
        statuses = (session or {}).get("Players") or {}
        present = [str(statuses.get(pid) or "").lower() in ("present","late") for pid in players]
        matrix.append([excel_date(match_date),excel_date(match_date),str(fixture.get("Opposition") or ""),*present,sum(1 for v in present if v)])
    old_last_row = max(sheet.used_range.last_cell.row,2)
    old_last_col = max(sheet.used_range.last_cell.column,len(headers))
    sheet.range((1,1),(old_last_row,old_last_col)).clear_contents()
    sheet.range((1,1),(len(matrix),len(headers))).value = matrix
    try:
        table = sheet.tables[table_name]
        table.resize(sheet.range((1,1),(max(len(matrix),2),len(headers))))
    except Exception:
        table = sheet.tables.add(sheet.range((1,1),(max(len(matrix),2),len(headers))), name=table_name)
    if len(matrix)==1: sheet.range((2,1),(2,len(headers))).clear_contents()
    sheet.range("A:A").number_format="dd-mm-yy"
    sheet.range("B:B").number_format="dddd"
    return len(fixtures)


def refresh_training_attendance_sheet(book) -> int:
    sheet_name="Training Attendance"; table_name="Training_Attendance"
    if sheet_name not in [s.name for s in book.sheets]: return 0
    sheet=book.sheets[sheet_name]; players=active_player_ids(book); sessions=latest_attendance_sessions(book,"Training")
    headers=["Date","Day","Session",*players,"Count"]; matrix=[headers]
    for session in sessions:
        d=session.get("SessionDate"); statuses=session.get("Players") or {}
        present=[str(statuses.get(pid) or "").lower() in ("present","late") for pid in players]
        matrix.append([excel_date(d),excel_date(d),"Training",*present,sum(1 for v in present if v)])
    old_last_row=max(sheet.used_range.last_cell.row,2); old_last_col=max(sheet.used_range.last_cell.column,len(headers))
    sheet.range((1,1),(old_last_row,old_last_col)).clear_contents(); sheet.range((1,1),(len(matrix),len(headers))).value=matrix
    try:
        table=sheet.tables[table_name]; table.resize(sheet.range((1,1),(max(len(matrix),2),len(headers))))
    except Exception:
        table=sheet.tables.add(sheet.range((1,1),(max(len(matrix),2),len(headers))),name=table_name)
    if len(matrix)==1: sheet.range((2,1),(2,len(headers))).clear_contents()
    sheet.range("A:A").number_format="dd-mm-yy"; sheet.range("B:B").number_format="dddd"
    return len(sessions)


def refresh_wide_attendance_sheets(book) -> dict[str,int]:
    return {"matchRows":refresh_match_attendance_sheet(book),"trainingRows":refresh_training_attendance_sheet(book)}


def ensure_matchday_table(book):
    names=[s.name for s in book.sheets]
    sheet=book.sheets[MATCHDAY_SHEET] if MATCHDAY_SHEET in names else book.sheets.add(MATCHDAY_SHEET,after=book.sheets[-1])
    try: return sheet,sheet.tables[MATCHDAY_TABLE]
    except Exception:
        sheet.range("A1").value=[MATCHDAY_HEADERS]
        table=sheet.tables.add(sheet.range((1,1),(2,len(MATCHDAY_HEADERS))),name=MATCHDAY_TABLE)
        sheet.range((2,1),(2,len(MATCHDAY_HEADERS))).clear_contents(); return sheet,table


def player_lookup(payload: dict[str,Any]) -> dict[str,str]:
    lookup={}
    for p in payload.get("squad") or []:
        if p.get("playerId"): lookup[str(p["playerId"])]=str(p.get("displayName") or p["playerId"])
    return lookup


def matchday_rows(session: dict[str,Any]) -> list[dict[str,Any]]:
    payload=session.get("payload") or {}; fixture=payload.get("fixture") or {}; sid=str(session.get("id"))
    match_id=payload.get("matchId") or session.get("match_id") or ""; match_date=fixture.get("date") or session.get("match_date") or ""
    opposition=fixture.get("opposition") or session.get("opposition") or ""; competition=fixture.get("competition") or session.get("competition") or ""
    submitted_by=payload.get("submittedBy") or session.get("submitted_by") or ""; started_at=payload.get("startedAt") or session.get("started_at") or ""; finished_at=payload.get("finishedAt") or session.get("finished_at") or ""
    names=player_lookup(payload); rows=[]
    def add(kind,suffix,player_id="",related_id="",minute="",detail="",value=""):
        rows.append({"ImportKey":f"{sid}|{suffix}","SessionId":sid,"MatchId":match_id,"MatchDate":match_date,"Opposition":opposition,"Competition":competition,"RecordType":kind,"PlayerId":player_id,"DisplayName":names.get(str(player_id),str(player_id) if player_id else ""),"RelatedPlayerId":related_id,"RelatedDisplayName":names.get(str(related_id),str(related_id) if related_id else ""),"Minute":minute,"Detail":detail,"Value":value,"SubmittedBy":submitted_by,"StartedAt":started_at,"FinishedAt":finished_at,"Source":"Matchday App"})
    add("Session","session",detail=f"{opposition} · {competition}")
    for i,pid in enumerate(payload.get("starters") or []): add("Starter",f"starter-{i}-{pid}",player_id=pid,value=1)
    for i,sub in enumerate(payload.get("substitutions") or []): add("Substitution",f"sub-{i}",player_id=sub.get("off") or "",related_id=sub.get("on") or "",minute=sub.get("minute","") ,detail="OFF → ON")
    for i,event in enumerate(payload.get("events") or []):
        etype=event.get("type") or "Event"
        if etype=="Goal":
            add("Goal",f"event-{i}",player_id=event.get("playerId") or "",related_id=event.get("assistPlayerId") or "",minute=event.get("minute","") ,detail=event.get("goalType") or "Goal",value=1)
            if event.get("assistPlayerId"): add("Assist",f"assist-{i}",player_id=event.get("assistPlayerId"),related_id=event.get("playerId") or "",minute=event.get("minute","") ,detail=f"Assist for {names.get(str(event.get('playerId')),event.get('playerId'))}",value=1)
        elif etype=="Card": add("Card",f"event-{i}",player_id=event.get("playerId") or "",minute=event.get("minute","") ,detail=event.get("cardType") or "Card",value=1)
        elif etype=="Note": add("Note",f"event-{i}",player_id=event.get("playerId") or "",minute=event.get("minute","") ,detail=event.get("text") or "")
        else: add(str(etype),f"event-{i}",player_id=event.get("playerId") or "",minute=event.get("minute","") ,detail=json.dumps(event,ensure_ascii=False))
    for i,stat in enumerate(payload.get("playerStats") or []):
        pid=stat.get("playerId") or ""
        if pid and stat.get("displayName"): names[str(pid)]=str(stat["displayName"])
        add("Minutes",f"minutes-{i}-{pid}",player_id=pid,detail="Starter" if stat.get("starter") else "Squad",value=stat.get("minutesPlayed",0))
    for row in rows:
        if row["PlayerId"]: row["DisplayName"]=names.get(str(row["PlayerId"]),row["DisplayName"])
        if row["RelatedPlayerId"]: row["RelatedDisplayName"]=names.get(str(row["RelatedPlayerId"]),row["RelatedDisplayName"])
    return rows


def excel_row_for_match(sheet, match_date: str, opposition: str) -> int | None:
    used=sheet.used_range.value
    if not used: return None
    if not isinstance(used[0],list): used=[used]
    wanted_date=iso_date(match_date); wanted_opp=str(opposition or "").strip().lower()
    for idx,row in enumerate(used[1:],start=2):
        if len(row)<2: continue
        if iso_date(row[0])==wanted_date and str(row[1] or "").strip().lower()==wanted_opp: return idx
    return None


def player_column(sheet, display_name: str) -> int | None:
    headers=sheet.range((1,1),(1,sheet.used_range.last_cell.column)).value
    if not isinstance(headers,list): headers=[headers]
    wanted=str(display_name or "").strip().lower()
    for idx,header in enumerate(headers,start=1):
        if str(header or "").strip().lower()==wanted: return idx
    return None


def increment_stat(sheet,row:int,col:int,amount:int=1):
    cell=sheet.range((row,col))
    try: value=int(cell.value or 0)
    except Exception: value=0
    cell.value=value+amount


def append_event_text(sheet,row:int,col:int,text:str):
    cell=sheet.range((row,col)); current=str(cell.value or "").strip(); cell.value=f"{current} | {text}" if current else text


def apply_matchday_to_summary_sheets(book,session:dict[str,Any]) -> list[str]:
    # Legacy path retained for compatibility; authoritative importer is preferred.
    return []


def import_matchday(book) -> tuple[int,int,list[str]]:
    sessions=api_get("matchday_sessions","id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload","finished_at.asc")
    sheet,table=ensure_matchday_table(book); existing=table_existing_column_values(table,"SessionId"); new_rows=[]; count=0
    for session in sessions:
        sid=str(session.get("id"))
        if not sid or sid in existing: continue
        new_rows.extend(matchday_rows(session)); existing.add(sid); count+=1
    return count,append_table_rows(sheet,table,new_rows),[]


def main() -> None:
    if len(sys.argv)!=2: raise SystemExit("Usage: python sync_supabase_to_excel.py /path/to/workbook.xlsx")
    workbook_path=Path(sys.argv[1]).expanduser().resolve()
    if not workbook_path.exists(): raise FileNotFoundError(workbook_path)
    try: import xlwings as xw
    except ImportError as exc: raise RuntimeError("xlwings is not installed. Run: python -m pip install xlwings") from exc
    app=None; book=None
    try:
        app=xw.App(visible=False,add_book=False); app.display_alerts=False; app.screen_updating=False
        book=app.books.open(str(workbook_path),update_links=False,read_only=False)
        attendance_rows=import_attendance(book); attendance_views=refresh_wide_attendance_sheets(book); matchday_sessions,matchday_rows_added,warnings=import_matchday(book); book.save()
        print("SUPABASE_SYNC_SUMMARY="+json.dumps({"attendanceRows":attendance_rows,"matchAttendanceRows":attendance_views.get("matchRows",0),"trainingAttendanceRows":attendance_views.get("trainingRows",0),"matchdaySessions":matchday_sessions,"matchdayRows":matchday_rows_added,"warnings":warnings},ensure_ascii=False))
    finally:
        if book is not None:
            try: book.close()
            except Exception: pass
        if app is not None:
            try: app.quit()
            except Exception: pass


if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(f"SUPABASE SYNC FAILED: {exc}",file=sys.stderr); sys.exit(1)
