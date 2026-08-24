#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def read_json(name: str, default: Any):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, payload: Any) -> None:
    (DATA / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return "kieran-d" if pid == "keiran-d" else pid


def canonical_name(pid: str, value: Any) -> str:
    if pid == "kieran-d":
        return "Kieran"
    return str(value or pid).strip()


def main() -> None:
    attendance = read_json("attendance.json", {"team": "Welling United Red OBDSFL", "season": "2026/27", "sessions": []})
    minutes = read_json("minutes.json", [])
    matches = read_json("matches.json", [])

    sessions = attendance.setdefault("sessions", [])
    match_lookup = {str(m.get("id") or ""): m for m in matches}

    groups: dict[str, dict[str, Any]] = {}
    for row in minutes:
        try:
            played = float(row.get("minutes") or 0)
        except (TypeError, ValueError):
            played = 0
        if played <= 0:
            continue
        match_id = str(row.get("matchId") or "").strip()
        date = str(row.get("date") or "")[:10]
        if not match_id or not date:
            continue
        group = groups.setdefault(match_id, {
            "date": date,
            "opposition": str(row.get("opposition") or ""),
            "players": {},
        })
        pid = canonical_id(row.get("playerId"))
        if pid:
            group["players"][pid] = canonical_name(pid, row.get("displayName"))

    for match_id, group in groups.items():
        date = group["date"]
        fixture = match_lookup.get(match_id, {})
        session = next((s for s in sessions if str(s.get("type") or "").lower() == "match" and str(s.get("date") or "")[:10] == date), None)
        if session is None:
            session = {
                "sessionKey": f"matchday-{match_id}",
                "sessionId": f"matchday-{match_id}",
                "date": date,
                "type": "Match",
                "venue": fixture.get("homeAway") or fixture.get("venue"),
                "submittedBy": "Matchday App",
                "submittedAt": None,
                "records": [],
            }
            sessions.append(session)

        records = session.setdefault("records", [])
        by_id: dict[str, dict[str, Any]] = {}
        duplicate_indexes: list[int] = []
        for index, record in enumerate(records):
            pid = canonical_id(record.get("playerId"))
            if not pid:
                continue
            record["playerId"] = pid
            record["displayName"] = canonical_name(pid, record.get("displayName"))
            if pid in by_id:
                duplicate_indexes.append(index)
            else:
                by_id[pid] = record

        for index in reversed(duplicate_indexes):
            records.pop(index)

        for pid, display_name in group["players"].items():
            record = by_id.get(pid)
            if record is None:
                record = {
                    "playerId": pid,
                    "displayName": display_name,
                    "status": "Present",
                    "source": "Matchday App",
                }
                records.append(record)
                by_id[pid] = record
            else:
                record["displayName"] = display_name
                record["status"] = "Present"
                record["source"] = "Matchday App"

    sessions.sort(key=lambda s: (str(s.get("date") or ""), str(s.get("type") or ""), str(s.get("sessionKey") or "")))
    write_json("attendance.json", attendance)
    print(f"  + Matchday appearances merged into attendance for {len(groups)} completed fixture(s).")


if __name__ == "__main__":
    main()
