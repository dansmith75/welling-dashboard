#!/usr/bin/env python3
"""Build/refresh an Excel squad-selection model."""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

SHEET_NAME = "Squad Selection"


def truthy(value: Any) -> bool:
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)): return value != 0
    return str(value or "").strip().lower() in {"true","yes","y","1","active"}


def to_date(value: Any):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        try:
            from datetime import timedelta
            return (datetime(1899,12,30)+timedelta(days=float(value))).date()
        except Exception: pass
    if value in (None,""): return None
    text=str(value)[:10]
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return datetime.strptime(text,fmt).date()
        except ValueError: pass
    return None


def table_rows(book,sheet_name,table_name=None):
    if sheet_name not in [s.name for s in book.sheets]: return []
    sheet=book.sheets[sheet_name]
    try: table=sheet.tables[table_name] if table_name else sheet.tables[0]
    except Exception: return []
    values=table.range.value
    if not values: return []
    if not isinstance(values[0],list): values=[values]
    headers=[str(v or "").strip() for v in values[0]]; out=[]
    for raw in values[1:]:
        if not raw or all(v in (None,"") for v in raw): continue
        out.append({headers[i]: raw[i] if i<len(raw) else "" for i in range(len(headers))})
    return out


def next_fixture(book):
    today=date.today(); candidates=[]
    for row in table_rows(book,"Fixtures","Fixtures"):
        d=to_date(row.get("Date"))
        if d and not truthy(row.get("Postponed")):
            candidates.append((d,str(row.get("Opposition") or "")))
    future=[x for x in candidates if x[0]>=today]
    return min(future or candidates,default=(today,""),key=lambda x:x[0])


def existing_settings(book):
    defaults={"match_date":None,"squad_size":16,"base":100,"training_bonus":25,"latest_late_penalty":10,"late_penalty":3,"minutes_factor":0.10}
    bias,override={},{}
    if SHEET_NAME not in [s.name for s in book.sheets]: return defaults,bias,override
    sh=book.sheets[SHEET_NAME]
    try:
        defaults["match_date"]=to_date(sh.range("B2").value)
        defaults["squad_size"]=int(sh.range("B3").value or 16)
        defaults["base"]=float(sh.range("B4").value or 100)
        defaults["training_bonus"]=float(sh.range("B5").value or 25)
        defaults["latest_late_penalty"]=float(sh.range("B6").value or 10)
        defaults["late_penalty"]=float(sh.range("B7").value or 3)
        defaults["minutes_factor"]=float(sh.range("B8").value or 0.10)
        values=sh.used_range.value or []
        if values and isinstance(values[0],list):
            headers=[str(x or "").strip() for x in values[10]] if len(values)>10 else []
            if "Player ID" in headers:
                pid_col=headers.index("Player ID"); bias_col=headers.index("Manager Bias") if "Manager Bias" in headers else None; over_col=headers.index("Override") if "Override" in headers else None
                for row in values[11:]:
                    if pid_col>=len(row): continue
                    pid=str(row[pid_col] or "").strip()
                    if not pid: continue
                    if bias_col is not None and bias_col<len(row): bias[pid]=row[bias_col] or 0
                    if over_col is not None and over_col<len(row): override[pid]=str(row[over_col] or "AUTO").upper()
    except Exception: pass
    return defaults,bias,override


def fee_lookup(book,match_date):
    if not match_date:return {}
    months={9:"Sept",10:"Oct",11:"Nov",12:"Dec",1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"June",7:"July",8:"Aug"}; month=months[match_date.month]; out={}
    for row in table_rows(book,"Monthly Fees"):
        name=str(row.get("Name") or "").strip()
        if name: out[name]=row.get(month)
    return out


def fee_ok(value,match_date):
    if match_date and match_date.month in (7,8): return True,"No fee month"
    if isinstance(value,(int,float)): return value>=25,str(value)
    text=str(value or "").strip(); ok=text.lower() in {"paid","yes","y","true","25","£25","✓"}; return ok,text or "Not recorded"


def training_metrics(book,match_date):
    rows=table_rows(book,"AttendanceRecords","AttendanceRecords"); by_player={}; latest_date=None; training_rows=[]
    for row in rows:
        if str(row.get("SessionType") or "").strip().lower()!="training": continue
        d=to_date(row.get("SessionDate"))
        if not d or (match_date and d>match_date): continue
        training_rows.append((d,row)); latest_date=d if latest_date is None or d>latest_date else latest_date
    for d,row in training_rows:
        pid=str(row.get("PlayerId") or "").strip()
        if pid=="keiran-d": pid="kieran-d"
        if not pid: continue
        m=by_player.setdefault(pid,{"latest_status":"No record","lates":0,"attended":0,"sessions":0}); status=str(row.get("Status") or "").strip(); m["sessions"]+=1
        if status.lower() in {"present","late"}:m["attended"]+=1
        if status.lower()=="late":m["lates"]+=1
        if d==latest_date:m["latest_status"]=status or "No record"
    return latest_date,by_player


def minutes_lookup(book):
    totals={}
    for row in table_rows(book,"MatchdayRecords","MatchdayRecords"):
        if str(row.get("RecordType") or "").strip().lower()!="minutes":continue
        pid=str(row.get("PlayerId") or "").strip()
        if pid=="keiran-d":pid="kieran-d"
        if not pid:continue
        try:totals[pid]=totals.get(pid,0)+float(row.get("Value") or 0)
        except Exception:pass
    return totals


def build(book):
    settings,saved_bias,saved_override=existing_settings(book); default_match,_=next_fixture(book); today=date.today()
    saved_match=settings["match_date"]
    # Preserve a manager-selected future fixture, but automatically advance a stale/played date.
    match_date=saved_match if saved_match and saved_match>=today else default_match
    squad=[]
    for row in table_rows(book,"Squad","Squad"):
        pid=str(row.get("ID") or "").strip()
        if pid=="keiran-d":pid="kieran-d"
        if not pid or not truthy(row.get("Active")):continue
        squad.append({"id":pid,"name":str(row.get("Display Name") or row.get("Name") or pid),"position":str(row.get("Position") or "")})
    fees=fee_lookup(book,match_date); latest_training,training=training_metrics(book,match_date); minutes=minutes_lookup(book); max_minutes=max([minutes.get(p["id"],0) for p in squad] or [0])
    if SHEET_NAME in [s.name for s in book.sheets]: sh=book.sheets[SHEET_NAME]; sh.clear()
    else: sh=book.sheets.add(SHEET_NAME,after=book.sheets["Squad"])
    sh.range("A1:Q1").merge(); sh.range("A1").value="Squad Selection / Rotation"; sh.range("A1:Q1").color="#C00000"; sh.range("A1:Q1").api.Font.Color=0xFFFFFF; sh.range("A1:Q1").api.Font.Bold=True; sh.range("A1:Q1").api.Font.Size=16
    labels=[["Next Match Date",match_date],["Squad Size",settings["squad_size"]],["Base Score",settings["base"]],["Training Attendance Bonus",settings["training_bonus"]],["Latest Training Late Penalty",settings["latest_late_penalty"]],["Penalty per Training Late",settings["late_penalty"]],["Minutes Catch-up per Minute",settings["minutes_factor"]],["Latest Training Used",latest_training or "No training record"],["Rule","Fees + latest training are hard gates. Score then favours lower minutes; Manager Bias/Override is yours."]]
    sh.range("A2:B10").value=labels; sh.range("A2:A10").api.Font.Bold=True; sh.range("B2").number_format="dd-mm-yy"; sh.range("B9").number_format="dd-mm-yy"
    headers=["Rank","Player ID","Player","Position","Fee Entry","Fees OK","Last Training","At Training","Latest Late","Training Lates","Total Minutes","Minutes Behind","Score","Manager Bias","Override","Eligible","Recommendation"]
    sh.range("A11:Q11").value=[headers]; sh.range("A11:Q11").color="#202020"; sh.range("A11:Q11").api.Font.Color=0xFFFFFF; sh.range("A11:Q11").api.Font.Bold=True
    start=12
    for i,p in enumerate(squad,start=start):
        fm=fees.get(p["name"]); fok,fentry=fee_ok(fm,match_date); tm=training.get(p["id"],{}); last_status=tm.get("latest_status","No record"); at_training=str(last_status).lower() in {"present","late"}; latest_late=str(last_status).lower()=="late"; late_count=int(tm.get("lates",0)); mins=float(minutes.get(p["id"],0)); behind=max_minutes-mins; bias=saved_bias.get(p["id"],0); override=saved_override.get(p["id"],"AUTO")
        sh.range(f"B{i}:L{i}").value=[[p["id"],p["name"],p["position"],fentry,fok,last_status,at_training,latest_late,late_count,mins,behind]]; sh.range(f"N{i}").value=bias; sh.range(f"O{i}").value=override; sh.range(f"P{i}").formula=f'=AND(F{i}=TRUE,H{i}=TRUE)'; sh.range(f"M{i}").formula=f'=IF(P{i}=FALSE,-999,$B$4+IF(H{i},$B$5,0)-IF(I{i},$B$6,0)-(J{i}*$B$7)+(L{i}*$B$8)+N{i})'; sh.range(f"A{i}").formula=f'=IF(P{i}=FALSE,"",RANK.EQ(M{i},$M${start}:$M${start+len(squad)-1},0))'; sh.range(f"Q{i}").formula=f'=IF(O{i}="SELECT","SELECT",IF(O{i}="ROTATE","ROTATE",IF(F{i}=FALSE,"HOLD - FEES",IF(H{i}=FALSE,"HOLD - TRAINING",IF(A{i}<=$B$3,"SELECT","ROTATE")))))'
    end=start+len(squad)-1
    if end>=start:
        validation=sh.range(f"O{start}:O{end}").api.Validation
        try:validation.Delete()
        except Exception:pass
        validation.Add(3,1,1,"AUTO,SELECT,ROTATE"); sh.range(f"N{start}:N{end}").color="#FFF2CC"; sh.range(f"O{start}:O{end}").color="#FFF2CC"; sh.range(f"F{start}:Q{end}").api.HorizontalAlignment=-4108
    sh.range("A:Q").api.Columns.AutoFit()
    for col,width in {"B":15,"C":16,"D":14,"E":14,"G":14,"Q":18}.items():sh.range(f"{col}:{col}").column_width=width
    book.save(); print(f"Squad Selection refreshed: {len(squad)} active players, match {match_date}, latest training {latest_training}")


def main():
    if len(sys.argv)!=2:raise SystemExit("Usage: python refresh_squad_selection.py /path/to/workbook.xlsx")
    path=Path(sys.argv[1]).expanduser().resolve(); import xlwings as xw; app=xw.App(visible=False,add_book=False); app.display_alerts=False; app.screen_updating=False; book=None
    try:book=app.books.open(str(path),update_links=False,read_only=False); build(book)
    finally:
        if book is not None:book.close()
        app.quit()

if __name__=="__main__":main()
