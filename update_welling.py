#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

WORKBOOK_NAME = "Welling United Red OBDSFL 26-27.xlsx"
EXPECTED = ["players.json", "matches.json", "goals.json", "assists.json", "events.json", "attendance.json", "minutes.json", "timeline.json"]
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = ROOT / ".welling-cache"
EXPORT_SNAPSHOT = CACHE / "Welling-dashboard-export.xlsx"


def run(args, check=True, capture=False):
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=capture)


def ensure_python_package(import_name: str, pip_name: str | None = None):
    if importlib.util.find_spec(import_name) is not None:
        return
    package = pip_name or import_name
    print(f"Installing one-time helper: {package}...")
    run([sys.executable, "-m", "pip", "install", package])


def find_workbook() -> Path:
    candidates = []
    env_path = os.environ.get("WELLING_WORKBOOK_PATH")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    one_drive = os.environ.get("OneDrive") or os.environ.get("OneDriveConsumer")
    if one_drive:
        candidates.append(Path(one_drive) / "Documents" / "Dan" / "Football" / WORKBOOK_NAME)
    candidates.extend([
        Path.home() / "OneDrive" / "Documents" / "Dan" / "Football" / WORKBOOK_NAME,
        Path.home() / "OneDrive - Personal" / "Documents" / "Dan" / "Football" / WORKBOOK_NAME,
        Path.home() / "Library" / "CloudStorage" / "OneDrive-Personal" / "Documents" / "Dan" / "Football" / WORKBOOK_NAME,
        Path.home() / "Documents" / "Dan" / "Football" / WORKBOOK_NAME,
    ])
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if cloud_storage.exists():
        candidates.extend(cloud_storage.glob(f"OneDrive*/Documents/Dan/Football/{WORKBOOK_NAME}"))
    for path in candidates:
        if path.exists():
            return path
    print("\nI couldn't find the master workbook automatically.")
    entered = input("Paste the full path to the .xlsx workbook: ").strip().strip('"')
    path = Path(entered).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot():
    return {name: read_json(DATA / name) if (DATA / name).exists() else None for name in EXPECTED}


def player_summary(old, new):
    old_map = {str(p.get("id")): p for p in (old or []) if p.get("id")}
    new_map = {str(p.get("id")): p for p in (new or []) if p.get("id")}
    lines = []
    for pid in sorted(new_map.keys() - old_map.keys()):
        lines.append(f"  + Player added: {new_map[pid].get('displayName', pid)}")
    for pid in sorted(old_map.keys() - new_map.keys()):
        lines.append(f"  - Player removed: {old_map[pid].get('displayName', pid)}")
    for pid in sorted(new_map.keys() & old_map.keys()):
        a, b = old_map[pid], new_map[pid]
        name = b.get("displayName", pid)
        if a.get("active") != b.get("active"):
            lines.append(f"  * {name}: {'activated' if b.get('active') else 'made inactive'}")
        if a.get("displayName") != b.get("displayName"):
            lines.append(f"  * Name: {a.get('displayName')} -> {b.get('displayName')}")
        if a.get("position") != b.get("position"):
            lines.append(f"  * {name}: position {a.get('position') or '(blank)'} -> {b.get('position') or '(blank)'}")
    return lines


def match_summary(old, new):
    old_map = {str(m.get("id")): m for m in (old or []) if m.get("id")}
    new_map = {str(m.get("id")): m for m in (new or []) if m.get("id")}
    lines = []
    for mid in sorted(new_map.keys() - old_map.keys()):
        m = new_map[mid]
        lines.append(f"  + Fixture added: {m.get('date')} v {m.get('opposition')}")
    for mid in sorted(old_map.keys() - new_map.keys()):
        m = old_map[mid]
        lines.append(f"  - Fixture removed: {m.get('date')} v {m.get('opposition')}")
    watched = ["date", "opposition", "competition", "venue", "postponed", "goalsFor", "goalsAgainst", "result"]
    for mid in sorted(new_map.keys() & old_map.keys()):
        a, b = old_map[mid], new_map[mid]
        changed = [key for key in watched if a.get(key) != b.get(key)]
        if changed:
            score = ""
            if b.get("goalsFor") is not None or b.get("goalsAgainst") is not None:
                score = f" [{b.get('goalsFor')}-{b.get('goalsAgainst')}]"
            lines.append(f"  * Fixture updated: {b.get('date')} v {b.get('opposition')}{score} ({', '.join(changed)})")
    return lines


def sync_supabase(workbook: Path) -> dict:
    ensure_python_package("xlwings")
    print("2/10 Pulling Attendance / Matchday submissions from Supabase into Excel...")
    result = run([sys.executable, str(ROOT / "sync_supabase_via_excel.py"), str(workbook)], capture=True)
    if result.stdout:
        for line in result.stdout.splitlines():
            if not line.startswith("SUPABASE_SYNC_SUMMARY="):
                print(line)
    marker = "SUPABASE_SYNC_SUMMARY="
    summary_line = next((line for line in result.stdout.splitlines() if line.startswith(marker)), None)
    if not summary_line:
        return {"attendanceRows": 0, "matchdaySessions": 0, "matchdayRows": 0, "warnings": []}
    return json.loads(summary_line[len(marker):])


def create_export_snapshot(workbook: Path) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    temp_snapshot = CACHE / "Welling-dashboard-export.new.xlsx"
    try:
        temp_snapshot.unlink(missing_ok=True)
        result = run([sys.executable, str(ROOT / "create_workbook_snapshot.py"), str(workbook), str(temp_snapshot)], capture=True)
        if result.stdout:
            for line in result.stdout.splitlines():
                if not line.startswith("SNAPSHOT_CREATED="):
                    print(line)
        if not temp_snapshot.exists() or temp_snapshot.stat().st_size == 0:
            raise RuntimeError("Snapshot helper returned without creating a usable workbook")
        temp_snapshot.replace(EXPORT_SNAPSHOT)
        print(f"  + Local export snapshot refreshed: {EXPORT_SNAPSHOT}")
        return EXPORT_SNAPSHOT
    except Exception as exc:
        temp_snapshot.unlink(missing_ok=True)
        if EXPORT_SNAPSHOT.exists() and EXPORT_SNAPSHOT.stat().st_size > 0:
            stamp = datetime.fromtimestamp(EXPORT_SNAPSHOT.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  ! Could not refresh the local workbook snapshot: {exc}")
            print(f"  ! Using last successful snapshot from {stamp} instead.")
            return EXPORT_SNAPSHOT
        raise RuntimeError("Could not create an export snapshot and there is no previous snapshot to fall back to.") from exc


def tracked_non_data_changes() -> list[str]:
    output = run(["git", "status", "--porcelain", "--untracked-files=no"], capture=True).stdout
    changes = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().replace("\\", "/") if len(line) >= 4 else ""
        if path.startswith("data/"):
            continue
        changes.append(line)
    return changes


def main():
    print("\n============================================")
    print(" Welling Dashboard - Update")
    print("============================================\n")
    print("1/10 Syncing latest website code from GitHub...")
    run(["git", "pull", "--ff-only"])
    status = tracked_non_data_changes()
    if status:
        raise RuntimeError("Tracked local repo changes exist outside generated data files. Commit/revert them before publishing football data.")

    workbook = find_workbook()
    print(f"\nMaster workbook: {workbook}")
    print("The workbook may stay open in Excel. The updater reconciles central submissions, exports a snapshot, reapplies completed Matchday authority, then validates before publish.\n")
    before = snapshot()

    sync_ok = True
    try:
        sync = sync_supabase(workbook)
    except subprocess.CalledProcessError as exc:
        sync_ok = False
        sync = {"attendanceRows": 0, "matchdaySessions": 0, "matchdayRows": 0, "warnings": []}
        if EXPORT_SNAPSHOT.exists() and EXPORT_SNAPSHOT.stat().st_size > 0:
            stamp = datetime.fromtimestamp(EXPORT_SNAPSHOT.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print("\n  ! Excel reconciliation could not update the master workbook on this run.")
            print(f"  ! Dashboard publishing can continue from the last snapshot ({stamp}).")
        else:
            raise RuntimeError("Excel reconciliation failed and no previous export snapshot is available.") from exc

    print("\nSupabase → Excel")
    print("----------------")
    print(f"  + Attendance rows imported: {sync.get('attendanceRows', 0)}")
    print(f"  + Completed Matchdays reconciled: {sync.get('matchdaySessions', 0)}")
    print(f"  + Matchday audit rows rebuilt: {sync.get('matchdayRows', 0)}")
    for warning in sync.get("warnings", [])[:20]:
        print(f"  ! {warning}")

    print("\nPreparing local workbook snapshot for dashboard export...")
    export_workbook = create_export_snapshot(workbook) if sync_ok else EXPORT_SNAPSHOT

    print("\n3/10 Exporting snapshot to JSON...")
    run([sys.executable, str(ROOT / "export_welling_json.py"), "--workbook", str(export_workbook)])

    print("4/10 Applying authoritative completed Matchday data...")
    run([sys.executable, str(ROOT / "apply_matchday_authority.py")])

    print("5/10 Merging completed Matchday appearances into attendance...")
    run([sys.executable, str(ROOT / "merge_matchday_attendance.py")])

    print("6/10 Validating published data against completed Matchday sessions...")
    try:
        run([sys.executable, str(ROOT / "validate_dashboard_data.py")])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Dashboard validation failed. Publishing has been stopped; existing live data was not replaced.") from exc

    print("7/10 Validating required JSON files...")
    after = snapshot()
    for name in EXPECTED:
        if after[name] is None:
            raise RuntimeError(f"Missing export: data/{name}")

    changed = run(["git", "diff", "--name-only", "--", "data"], capture=True).stdout.splitlines()
    untracked_data = run(["git", "ls-files", "--others", "--exclude-standard", "--", "data"], capture=True).stdout.splitlines()
    changed = list(dict.fromkeys([*changed, *untracked_data]))
    if not changed:
        print("\nNo published football-data changes found. Data passed validation and there is nothing to push.\n")
        return

    print("\n============================================")
    print(" UPDATE SUMMARY")
    print("============================================")
    lines = player_summary(before["players.json"], after["players.json"])
    print("\nPlayers\n-------")
    print("\n".join(lines) if lines else "  No squad changes")
    lines = match_summary(before["matches.json"], after["matches.json"])
    print("\nFixtures / Results\n------------------")
    print("\n".join(lines) if lines else "  No fixture/result changes")
    print("\nOther data\n----------")
    labels = {"data/goals.json":"Goals","data/assists.json":"Assists","data/events.json":"Events","data/attendance.json":"Attendance","data/minutes.json":"Playing minutes","data/timeline.json":"Match timeline"}
    other = [f"  * {labels[p]} updated" for p in changed if p in labels]
    print("\n".join(other) if other else "  No other data changes")
    print("\nFiles to publish:")
    for path in changed:
        print(f"  - {path}")

    answer = input("\nPublish these VALIDATED updates to GitHub? [Y/N]: ").strip().lower()
    if answer != "y":
        print("\nCancelled. Nothing was committed or pushed.\n")
        return

    print("\n8/10 Staging changed JSON...")
    run(["git", "add", "data"])
    print("9/10 Committing...")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(["git", "commit", "-m", f"Update Welling data {stamp}"])
    print("10/10 Pushing to GitHub...")
    run(["git", "push"])
    print("\n============================================")
    print(" SUCCESS — VALIDATED")
    print("============================================")
    print("Completed Matchday result, timeline, scorers, assists, minutes and match attendance were checked against Supabase before publish.")
    print("GitHub Pages normally updates shortly afterwards.\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nUPDATE FAILED: {exc}\n")
        sys.exit(1)
