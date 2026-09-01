#!/usr/bin/env python3
"""Apply explicit match facts that are not available from Excel or Matchday.

These overrides are deliberately narrow. They preserve user-confirmed historic
facts through future workbook regenerations without adding guest players to the
normal squad or changing a squad member's active status.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OVERRIDES = DATA / "manual-match-overrides.json"


def read_json(name: str, default: Any) -> Any:
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(name: str, payload: Any) -> None:
    (DATA / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def find_match_row(rows: list[dict[str, Any]], override: dict[str, Any]) -> dict[str, Any] | None:
    match_id = str(override.get("matchId") or "")
    for row in rows:
        if str(row.get("id") or row.get("matchId") or "") == match_id:
            return row
    return next((row for row in rows if str(row.get("date") or "")[:10] == override["date"] and row.get("opposition") == override["opposition"]), None)


def upsert_stat(rows: list[dict[str, Any]], override: dict[str, Any], key: str) -> None:
    row = find_match_row(rows, override)
    if row is None:
        row = {
            "matchId": override["matchId"],
            "date": override["date"],
            "opposition": override["opposition"],
        }
        rows.append(row)
    # Manual facts supplement the workbook. This is especially important for
    # guest players, who have no permanent column on the wide Goals/Assists
    # sheets, while retaining any squad-player statistics entered in Excel.
    values = dict(row.get(key) or {})
    values.update(override.get(key, {}))
    row[key] = values


def main() -> None:
    if not OVERRIDES.exists():
        print("  + No manual match overrides configured.")
        return

    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    matches = read_json("matches.json", [])
    goals = read_json("goals.json", [])
    assists = read_json("assists.json", [])
    attendance = read_json("attendance.json", {"team": "Welling United Red OBDSFL", "season": "2026/27", "sessions": []})

    player_by_id = {str(player.get("id")): player for player in read_json("players.json", [])}
    for override in overrides:
        match = find_match_row(matches, override)
        if match is None:
            raise RuntimeError(f"Manual override fixture not found: {override['date']} v {override['opposition']}")
        match.update({key: override[key] for key in ("goalsFor", "goalsAgainst", "result")})
        upsert_stat(goals, override, "goals")
        upsert_stat(assists, override, "assists")

        sessions = attendance.setdefault("sessions", [])
        session = next((item for item in sessions if str(item.get("type") or "").lower() == "match" and str(item.get("date") or "")[:10] == override["date"]), None)
        if session is None:
            session = {
                "sessionKey": f"manual-{override['matchId']}",
                "sessionId": f"manual-{override['matchId']}",
                "date": override["date"],
                "type": "Match",
                "venue": match.get("homeAway") or match.get("venue"),
                "submittedBy": "Manual match authority",
                "submittedAt": None,
                "records": [],
            }
            sessions.append(session)
        records = session.setdefault("records", [])
        by_id = {str(record.get("playerId") or ""): record for record in records}
        for appearance in override.get("appearances", []):
            pid = str(appearance.get("playerId") or "")
            if not pid:
                continue
            record = by_id.get(pid)
            if record is None:
                record = {"playerId": pid}
                records.append(record)
            record.update({
                "displayName": appearance.get("displayName") or player_by_id.get(pid, {}).get("displayName") or pid,
                "status": "Present",
                "source": "Manual match authority",
            })

    attendance["sessions"].sort(key=lambda item: (str(item.get("date") or ""), str(item.get("type") or ""), str(item.get("sessionKey") or "")))
    write_json("matches.json", matches)
    write_json("goals.json", goals)
    write_json("assists.json", assists)
    write_json("attendance.json", attendance)
    print(f"  + Applied {len(overrides)} manual match override(s).")


if __name__ == "__main__":
    main()
