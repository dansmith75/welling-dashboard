#!/usr/bin/env python3
"""Overlay completed Supabase Matchday sessions onto generated Dashboard JSON.

Excel remains the long-term workbook store, but for any fixture with a completed
Matchday session the central Matchday payload is authoritative for result,
goals, assists, notes/cards, minutes and timeline. This prevents a stale or
blank Excel summary row from wiping a completed match from the Dashboard.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sync_supabase_to_excel import api_get

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def read_json(name: str, default):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, payload: Any) -> None:
    path = DATA / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  + Matchday authority applied: {path}")


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return "kieran-d" if pid == "keiran-d" else pid


def canonical_name(pid: Any, value: Any) -> str:
    if canonical_id(pid) == "kieran-d":
        return "Kieran"
    return str(value or canonical_id(pid) or "").strip()


def session_key(session: dict[str, Any]) -> str:
    payload = session.get("payload") or {}
    fixture = payload.get("fixture") or {}
    return str(payload.get("matchId") or session.get("match_id") or f"{fixture.get('date') or session.get('match_date')}|{fixture.get('opposition') or session.get('opposition')}")


def latest_completed_sessions() -> list[dict[str, Any]]:
    rows = api_get(
        "matchday_sessions",
        "id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload",
        "finished_at.asc",
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not (row.get("finished_at") or payload.get("finishedAt")):
            continue
        latest[session_key(row)] = row
    return list(latest.values())


def fixture_meta(session: dict[str, Any]) -> tuple[str, str, str, str]:
    payload = session.get("payload") or {}
    fixture = payload.get("fixture") or {}
    match_id = str(payload.get("matchId") or session.get("match_id") or "")
    date = str(fixture.get("date") or session.get("match_date") or "")[:10]
    opposition = str(fixture.get("opposition") or session.get("opposition") or "")
    competition = str(fixture.get("competition") or session.get("competition") or "")
    return match_id, date, opposition, competition


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


def find_row(rows: list[dict[str, Any]], match_id: str, date: str, opposition: str) -> dict[str, Any] | None:
    for row in rows:
        if match_id and str(row.get("matchId") or row.get("id") or "") == match_id:
            return row
    for row in rows:
        if str(row.get("date") or "")[:10] == date and str(row.get("opposition") or "") == opposition:
            return row
    return None


def score_from_events(events: list[dict[str, Any]]) -> tuple[int, int]:
    goals_for = 0
    goals_against = 0
    for event in events:
        kind = str(event.get("type") or "").strip().lower()
        if kind in ("goal", "own goal"):
            goals_for += 1
        elif kind == "opponent goal":
            goals_against += 1
    return goals_for, goals_against


def timeline_for_session(session: dict[str, Any]) -> dict[str, Any]:
    payload = session.get("payload") or {}
    match_id, date, opposition, competition = fixture_meta(session)
    names = names_for_payload(payload)
    timeline: list[dict[str, Any]] = []
    seq = 0

    def add(event: dict[str, Any]) -> None:
        nonlocal seq
        event["_seq"] = seq
        seq += 1
        timeline.append(event)

    for sub in payload.get("substitutions") or []:
        off_id = canonical_id(sub.get("off"))
        on_id = canonical_id(sub.get("on"))
        add({
            "type": "Substitution",
            "minute": sub.get("minute"),
            "playerId": off_id or None,
            "player": names.get(off_id, off_id) or None,
            "relatedPlayerId": on_id or None,
            "relatedPlayer": names.get(on_id, on_id) or None,
            "detail": "OFF → ON",
            "value": None,
            "source": "Matchday App",
        })

    for raw in payload.get("events") or []:
        kind = str(raw.get("type") or "Event")
        pid = canonical_id(raw.get("playerId"))
        related_id = canonical_id(raw.get("assistPlayerId"))
        detail = ""
        value: Any = None
        if kind == "Goal":
            detail = raw.get("goalType") or "Goal"
            value = 1
        elif kind == "Opponent Goal":
            detail = raw.get("goalType") or "Goal"
            value = 1
        elif kind == "Own Goal":
            detail = raw.get("goalType") or "Own Goal"
            value = 1
        elif kind == "Card":
            detail = raw.get("cardType") or "Card"
            value = 1
        elif kind == "Note":
            detail = raw.get("text") or ""
        else:
            detail = json.dumps(raw, ensure_ascii=False)

        add({
            "type": kind,
            "minute": raw.get("minute"),
            "playerId": pid or None,
            "player": names.get(pid, pid) or None,
            "relatedPlayerId": related_id or None,
            "relatedPlayer": names.get(related_id, related_id) or None,
            "detail": detail,
            "value": value,
            "source": "Matchday App",
        })

    def minute_value(event: dict[str, Any]) -> float:
        try:
            return float(event.get("minute"))
        except (TypeError, ValueError):
            return 9999.0

    timeline.sort(key=lambda event: (minute_value(event), event.get("_seq", 0)))
    for event in timeline:
        event.pop("_seq", None)

    return {
        "matchId": match_id,
        "date": date,
        "opposition": opposition,
        "competition": competition,
        "events": timeline,
    }


def main() -> None:
    sessions = latest_completed_sessions()
    if not sessions:
        print("  + No completed Matchday sessions to overlay.")
        return

    matches = read_json("matches.json", [])
    goals = read_json("goals.json", [])
    assists = read_json("assists.json", [])
    events_json = read_json("events.json", [])
    minutes = read_json("minutes.json", [])
    timeline = read_json("timeline.json", [])

    authoritative_ids: set[str] = set()
    authoritative_keys: set[tuple[str, str]] = set()
    new_minutes: list[dict[str, Any]] = []
    new_timelines: list[dict[str, Any]] = []

    for session in sessions:
        payload = session.get("payload") or {}
        match_id, date, opposition, competition = fixture_meta(session)
        if not date or not opposition:
            continue
        authoritative_ids.add(match_id)
        authoritative_keys.add((date, opposition))
        names = names_for_payload(payload)
        raw_events = payload.get("events") or []
        goals_for, goals_against = score_from_events(raw_events)
        result = "W" if goals_for > goals_against else "L" if goals_for < goals_against else "D"

        match = find_row(matches, match_id, date, opposition)
        if match is not None:
            match["goalsFor"] = goals_for
            match["goalsAgainst"] = goals_against
            match["result"] = result

        goal_counts: dict[str, int] = {}
        assist_counts: dict[str, int] = {}
        event_values: dict[str, str] = {}
        for event in raw_events:
            kind = str(event.get("type") or "")
            pid = canonical_id(event.get("playerId"))
            if kind == "Goal" and pid:
                goal_counts[pid] = goal_counts.get(pid, 0) + 1
                assist_id = canonical_id(event.get("assistPlayerId"))
                if assist_id:
                    assist_counts[assist_id] = assist_counts.get(assist_id, 0) + 1
            elif kind in ("Card", "Note") and pid:
                minute = event.get("minute")
                prefix = f"{minute}' " if minute not in (None, "") else ""
                detail = event.get("cardType") if kind == "Card" else event.get("text")
                text = f"{prefix}{detail or kind}"
                event_values[pid] = f"{event_values[pid]} | {text}" if pid in event_values else text

        goal_row = find_row(goals, match_id, date, opposition)
        if goal_row is None:
            goal_row = {"matchId": match_id, "date": date, "opposition": opposition, "goals": {}}
            goals.append(goal_row)
        goal_row["goals"] = goal_counts

        assist_row = find_row(assists, match_id, date, opposition)
        if assist_row is None:
            assist_row = {"matchId": match_id, "date": date, "opposition": opposition, "assists": {}}
            assists.append(assist_row)
        assist_row["assists"] = assist_counts

        event_row = find_row(events_json, match_id, date, opposition)
        if event_row is None:
            event_row = {"matchId": match_id, "date": date, "opposition": opposition, "events": {}}
            events_json.append(event_row)
        event_row["events"] = event_values

        session_id = str(session.get("id") or "")
        submitted_by = payload.get("submittedBy") or session.get("submitted_by") or ""
        for stat in payload.get("playerStats") or []:
            pid = canonical_id(stat.get("playerId"))
            if not pid:
                continue
            try:
                played = int(round(float(stat.get("minutesPlayed") or 0)))
            except (TypeError, ValueError):
                played = 0
            new_minutes.append({
                "sessionId": session_id,
                "matchId": match_id,
                "date": date,
                "opposition": opposition,
                "competition": competition,
                "playerId": pid,
                "displayName": names.get(pid, canonical_name(pid, stat.get("displayName"))),
                "minutes": played,
                "starter": bool(stat.get("starter")),
                "submittedBy": submitted_by,
            })

        new_timelines.append(timeline_for_session(session))

    def is_authoritative(row: dict[str, Any]) -> bool:
        mid = str(row.get("matchId") or "")
        key = (str(row.get("date") or "")[:10], str(row.get("opposition") or ""))
        return (mid and mid in authoritative_ids) or key in authoritative_keys

    minutes = [row for row in minutes if not is_authoritative(row)] + new_minutes
    timeline = [row for row in timeline if not is_authoritative(row)] + new_timelines
    minutes.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("displayName") or "")))
    timeline.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("opposition") or "")))

    write_json("matches.json", matches)
    write_json("goals.json", goals)
    write_json("assists.json", assists)
    write_json("events.json", events_json)
    write_json("minutes.json", minutes)
    write_json("timeline.json", timeline)
    print(f"  + {len(new_timelines)} completed Matchday fixture(s) are now authoritative.")


if __name__ == "__main__":
    main()
