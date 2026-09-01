#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sync_supabase_to_excel import api_get

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def read_json(name: str, default: Any):
    path = DATA / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_id(value: Any) -> str:
    pid = str(value or "").strip()
    return "kieran-d" if pid == "keiran-d" else pid


def match_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("date") or row.get("match_date") or "")[:10], str(row.get("opposition") or ""))


def main() -> None:
    players = read_json("players.json", [])
    matches = read_json("matches.json", [])
    goals = read_json("goals.json", [])
    assists = read_json("assists.json", [])
    minutes = read_json("minutes.json", [])
    timeline = read_json("timeline.json", [])
    attendance = read_json("attendance.json", {"sessions": []})
    manual_overrides = read_json("manual-match-overrides.json", [])

    match_by_id = {str(row.get("id") or ""): row for row in matches}
    goal_by_id = {str(row.get("matchId") or ""): row for row in goals}
    assist_by_id = {str(row.get("matchId") or ""): row for row in assists}
    timeline_by_id = {str(row.get("matchId") or ""): row for row in timeline}

    sessions = api_get(
        "matchday_sessions",
        "id,match_id,match_date,opposition,competition,submitted_by,started_at,finished_at,match_seconds,payload",
        "finished_at.asc",
    )
    completed = []
    latest = {}
    for session in sessions:
        payload = session.get("payload") or {}
        if not (session.get("finished_at") or payload.get("finishedAt")):
            continue
        mid = str(payload.get("matchId") or session.get("match_id") or "")
        if mid:
            latest[mid] = session
    completed = list(latest.values())

    errors: list[str] = []

    player_by_id = {canonical_id(player.get("id")): player for player in players}
    for override in manual_overrides:
        mid = str(override.get("matchId") or "")
        match = match_by_id.get(mid)
        label = f"{override.get('date')} v {override.get('opposition')}"
        if not match:
            errors.append(f"{label}: manual override fixture is missing")
            continue
        for key in ("goalsFor", "goalsAgainst", "result"):
            if match.get(key) != override.get(key):
                errors.append(f"{label}: manual {key} override was not applied")
        if (goal_by_id.get(mid) or {}).get("goals", {}) != override.get("goals", {}):
            errors.append(f"{label}: manual scorer override was not applied")
        if (assist_by_id.get(mid) or {}).get("assists", {}) != override.get("assists", {}):
            errors.append(f"{label}: manual assist override was not applied")
        for guest_id in override.get("goals", {}):
            if str(guest_id).startswith("guest-") and canonical_id(guest_id) in player_by_id:
                errors.append(f"{label}: guest scorer {guest_id} must not be in players.json")
        for appearance in override.get("appearances", []):
            pid = canonical_id(appearance.get("playerId"))
            if pid and player_by_id.get(pid, {}).get("active") is not False:
                errors.append(f"{label}: inactive appearance {pid} was unexpectedly reactivated")
    for session in completed:
        payload = session.get("payload") or {}
        fixture = payload.get("fixture") or {}
        mid = str(payload.get("matchId") or session.get("match_id") or "")
        date = str(fixture.get("date") or session.get("match_date") or "")[:10]
        opposition = str(fixture.get("opposition") or session.get("opposition") or "")
        raw_events = payload.get("events") or []
        raw_subs = payload.get("substitutions") or []
        expected_timeline_count = len(raw_events) + len(raw_subs)
        expected_for = sum(1 for e in raw_events if str(e.get("type") or "").lower() in ("goal", "own goal"))
        expected_against = sum(1 for e in raw_events if str(e.get("type") or "").lower() == "opponent goal")

        match = match_by_id.get(mid)
        if not match:
            errors.append(f"{date} v {opposition}: missing fixture row")
        else:
            if int(match.get("goalsFor") or 0) != expected_for or int(match.get("goalsAgainst") or 0) != expected_against:
                errors.append(f"{date} v {opposition}: score mismatch; expected {expected_for}-{expected_against}")

        tl = timeline_by_id.get(mid)
        actual_timeline_count = len((tl or {}).get("events") or [])
        if actual_timeline_count != expected_timeline_count:
            errors.append(f"{date} v {opposition}: timeline has {actual_timeline_count} items, expected {expected_timeline_count}")

        expected_goals: dict[str, int] = {}
        expected_assists: dict[str, int] = {}
        for event in raw_events:
            if str(event.get("type") or "") == "Goal":
                pid = canonical_id(event.get("playerId"))
                if pid:
                    expected_goals[pid] = expected_goals.get(pid, 0) + 1
                aid = canonical_id(event.get("assistPlayerId"))
                if aid:
                    expected_assists[aid] = expected_assists.get(aid, 0) + 1
        if (goal_by_id.get(mid) or {}).get("goals", {}) != expected_goals:
            errors.append(f"{date} v {opposition}: scorer totals do not match Matchday")
        if (assist_by_id.get(mid) or {}).get("assists", {}) != expected_assists:
            errors.append(f"{date} v {opposition}: assist totals do not match Matchday")

        played_ids = set()
        for stat in payload.get("playerStats") or []:
            try:
                played = float(stat.get("minutesPlayed") or 0)
            except (TypeError, ValueError):
                played = 0
            if played > 0:
                played_ids.add(canonical_id(stat.get("playerId")))

        minute_ids = {
            canonical_id(row.get("playerId"))
            for row in minutes
            if str(row.get("matchId") or "") == mid and float(row.get("minutes") or 0) > 0
        }
        if minute_ids != played_ids:
            errors.append(f"{date} v {opposition}: minutes/player list does not match Matchday")

        attendance_session = next((s for s in attendance.get("sessions", []) if str(s.get("type") or "").lower() == "match" and str(s.get("date") or "")[:10] == date), None)
        present_ids = set()
        for record in (attendance_session or {}).get("records", []):
            if str(record.get("status") or "").lower() in ("present", "late"):
                present_ids.add(canonical_id(record.get("playerId")))
        missing_attendance = played_ids - present_ids
        if missing_attendance:
            errors.append(f"{date} v {opposition}: played players missing from attendance: {', '.join(sorted(missing_attendance))}")

    if errors:
        print("\nDATA VALIDATION FAILED")
        for error in errors:
            print(f"  ! {error}")
        raise SystemExit(1)

    print(f"  + Data validation passed for {len(completed)} completed Matchday fixture(s).")


if __name__ == "__main__":
    main()
