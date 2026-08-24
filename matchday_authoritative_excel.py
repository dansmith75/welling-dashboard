#!/usr/bin/env python3
"""Authoritative completed-Matchday reconciliation into the Excel workbook."""
from __future__ import annotations
from typing import Any
import sync_supabase_to_excel as core


def normal(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return "kieran-d" if pid == "keiran-d" else pid


def canonical_name(pid: Any, value: Any) -> str:
    if canonical_id(pid) == "kieran-d": return "Kieran"
    return str(value or canonical_id(pid) or "").strip()


def latest_completed_sessions() -> list[dict[str, Any]]:
    rows=core.api_get("matchday_sessions","id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload","finished_at.asc")
    latest={}
    for row in rows:
        payload=row.get("payload") or {}
        if not (row.get("finished_at") or payload.get("finishedAt")): continue
        fixture=payload.get("fixture") or {}
        key=str(payload.get("matchId") or row.get("match_id") or f"{fixture.get('date') or row.get('match_date')}|{fixture.get('opposition') or row.get('opposition')}")
        latest[key]=row
    return list(latest.values())


def rebuild_matchday_records(book,sessions):
    sheet,table=core.ensure_matchday_table(book); headers=core.table_headers(table); rows=[]
    for session in sessions: rows.extend(core.matchday_rows(session))
    sr,sc=table.range.row,table.range.column; oldr=max(table.range.rows.count,2); oldc=max(table.range.columns.count,len(headers))
    sheet.range((sr+1,sc),(sr+oldr-1,sc+oldc-1)).clear_contents(); endr=max(len(rows)+1,2); table.resize(sheet.range((sr,sc),(sr+endr-1,sc+len(headers)-1)))
    if rows: sheet.range((sr+1,sc),(sr+len(rows),sc+len(headers)-1)).value=[[r.get(h,"") for h in headers] for r in rows]
    return len(rows)


def _headers(sheet):
    if hasattr(core,"sheet_headers"): return core.sheet_headers(sheet)
    values=sheet.range((1,1),(1,sheet.used_range.last_cell.column)).value
    if isinstance(values,list) and len(values)==1 and isinstance(values[0],list): values=values[0]
    return values if isinstance(values,list) else [values]


def find_header_column(sheet,*names):
    wanted={normal(n) for n in names}
    for idx,h in enumerate(_headers(sheet),start=1):
        if normal(h) in wanted:return idx
    return None


def squad_rows(book):
    if "Squad" not in [s.name for s in book.sheets]:return []
    try:return core.table_dict_rows(book.sheets["Squad"].tables["Squad"])
    except Exception:return []


def player_header_candidates(book,pid:str,matchday_name:str)->list[str]:
    pid=canonical_id(pid); out=[matchday_name]
    for row in squad_rows(book):
        if canonical_id(row.get("ID"))!=pid:continue
        out.extend([row.get("Display Name"),row.get("First Name"),row.get("Name")]); break
    first=pid.split("-",1)[0] if pid else ""
    if first: out.extend([first, first.title()])
    aliases={
        "alfie-f":["Alf","Alfie","Alfie F"],
        "kieran-d":["Kieran","Kieran D","Keiran","Keiran D"],
        "bailey-s":["Bailey"],"brad-e":["Brad","Brad E"],"darren-r":["Darren"],
        "frank-a":["Frank"],"george-h":["George H"],"george-w":["George W"],
        "josh-m":["Josh"],"jude-g":["Jude"],"kalan-w":["Kalan"],"liam-s":["Liam"],
        "rocco-b":["Rocco"],"ronnie-d":["Ronnie D"],"ronnie-t":["Ronnie T"],
        "ryan-b":["Ryan"],"ryeley-d":["Ryeley"],"will-b":["Will"]
    }
    out.extend(aliases.get(pid,[]))
    seen=[]; norms=set()
    for item in out:
        text=str(item or "").strip(); key=normal(text)
        if text and key and key not in norms: seen.append(text); norms.add(key)
    return seen


def player_column_for_id(book,sheet,pid:str,matchday_name:str):
    headers=_headers(sheet); candidates=player_header_candidates(book,pid,matchday_name); wanted={normal(x) for x in candidates}
    for idx,h in enumerate(headers,start=1):
        if normal(h) in wanted:return idx
    # Final safe fallback: match the first-name part of the stable ID only when
    # that produces one unique player column. This handles legacy headers such
    # as "Brad"/"Rocco" even if the Squad display name changed.
    first=normal(canonical_id(pid).split("-",1)[0])
    metadata={"date","opposition","count","total"}
    hits=[idx for idx,h in enumerate(headers,start=1) if normal(h) not in metadata and first and normal(h).startswith(first)]
    if len(hits)==1:return hits[0]
    return None


def set_audit_total(sheet,row:int):
    audit_col=find_header_column(sheet,"Count","Total")
    if not audit_col:return
    opp_col=find_header_column(sheet,"Opposition") or 2; first_col=opp_col+1; last_col=audit_col-1
    if last_col<first_col: sheet.range((row,audit_col)).value=0; return
    sheet.range((row,audit_col)).formula=f"=SUM({sheet.range((row,first_col)).address}:{sheet.range((row,last_col)).address})"


def names_for_payload(payload):
    names={}
    for p in payload.get("squad") or []:
        pid=canonical_id(p.get("playerId"))
        if pid:names[pid]=canonical_name(pid,p.get("displayName"))
    for stat in payload.get("playerStats") or []:
        pid=canonical_id(stat.get("playerId"))
        if pid:names[pid]=canonical_name(pid,stat.get("displayName"))
    return names


def overwrite_wide_stats(book,session):
    payload=session.get("payload") or {}; fixture=payload.get("fixture") or {}; match_date=fixture.get("date") or session.get("match_date") or ""; opposition=fixture.get("opposition") or session.get("opposition") or ""; names=names_for_payload(payload)
    goals={};assists={};events={};gf=0;ga=0
    for event in payload.get("events") or []:
        etype=str(event.get("type") or ""); pid=canonical_id(event.get("playerId"))
        if etype in ("Goal","Own Goal"):gf+=1
        elif etype=="Opponent Goal":ga+=1
        if etype=="Goal" and pid:
            goals[pid]=goals.get(pid,0)+1; aid=canonical_id(event.get("assistPlayerId"))
            if aid:assists[aid]=assists.get(aid,0)+1
        elif etype in ("Card","Note") and pid:
            minute=event.get("minute"); prefix=f"{minute}' " if minute not in (None,"") else ""; detail=event.get("cardType") if etype=="Card" else event.get("text"); text=f"{prefix}{detail or etype}"; events[pid]=f"{events[pid]} | {text}" if pid in events else text
    warnings=[]
    for sheet_name,values in (("Goals",goals),("Assists",assists),("Events",events)):
        if sheet_name not in [s.name for s in book.sheets]:warnings.append(f"Missing sheet: {sheet_name}");continue
        sheet=book.sheets[sheet_name]; row=core.excel_row_for_match(sheet,match_date,opposition)
        if row is None:warnings.append(f"No {sheet_name} row for {match_date} v {opposition}");continue
        headers=_headers(sheet)
        for col,header in enumerate(headers,start=1):
            if normal(header) in {"date","opposition","count","total"}:continue
            if str(header or "").strip():sheet.range((row,col)).clear_contents()
        for pid,value in values.items():
            display=names.get(pid,canonical_name(pid,pid)); col=player_column_for_id(book,sheet,pid,display)
            if col:sheet.range((row,col)).value=value
            else:warnings.append(f"Could not place {sheet_name[:-1].lower()}: {display} ({pid}) v {opposition}; headers={','.join(str(h or '') for h in headers)}")
        if sheet_name in ("Goals","Assists"):set_audit_total(sheet,row)
    if "Fixtures" in [s.name for s in book.sheets]:
        sheet=book.sheets["Fixtures"]; row=core.excel_row_for_match(sheet,match_date,opposition)
        if row is None:warnings.append(f"No Fixtures row for {match_date} v {opposition}")
        else:
            gf_col=find_header_column(sheet,"Goals For","GoalsFor","GF");ga_col=find_header_column(sheet,"Goals Against","GoalsAgainst","GA");result_col=find_header_column(sheet,"Result")
            if gf_col:sheet.range((row,gf_col)).value=gf
            if ga_col:sheet.range((row,ga_col)).value=ga
            if result_col:sheet.range((row,result_col)).value="W" if gf>ga else "L" if gf<ga else "D"
    return warnings


def import_matchday_authoritative(book):
    sessions=latest_completed_sessions();warnings=[]
    for session in sessions:warnings.extend(overwrite_wide_stats(book,session))
    return len(sessions),rebuild_matchday_records(book,sessions),warnings
