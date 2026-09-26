"""Apply the current FA Full-Time fixture schedule after each Excel export."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def normal(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def fixture_identity(row: dict) -> tuple[str, str, str]:
    return (normal(row.get("opposition")), normal(row.get("competition")), normal(row.get("homeAway")))


def main() -> None:
    matches_path = DATA / "matches.json"
    official_path = DATA / "official-fixtures.json"
    matches = json.loads(matches_path.read_text(encoding="utf-8"))
    official = json.loads(official_path.read_text(encoding="utf-8"))
    cutoff = min(row["date"] for row in official)
    existing_by_id = {str(row.get("id")): row for row in matches if row.get("id")}
    existing_by_identity = {fixture_identity(row): row for row in matches if row.get("opposition")}
    historical = [row for row in matches if str(row.get("date") or "") < cutoff]
    reconciled = []
    matched_ids: set[str] = set()
    for fixture in official:
        row = dict(fixture)
        prior = existing_by_id.get(str(fixture.get("id"))) or existing_by_identity.get(fixture_identity(fixture))
        if prior:
            # Excel is authoritative. Full-Time fills gaps but must not undo
            # dates, kick-offs, venues or postponements updated in Fixtures.
            row.update(prior)
            if prior.get("id"):
                matched_ids.add(str(prior["id"]))
        reconciled.append(row)
    for row in matches:
        if str(row.get("date") or "") < cutoff or str(row.get("id") or "") in matched_ids:
            continue
        if any(fixture_identity(item) == fixture_identity(row) for item in reconciled):
            continue
        reconciled.append(row)
    reconciled.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("opposition") or "")))
    matches_path.write_text(json.dumps(historical + reconciled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"- Applied {len(official)} official Full-Time fixture(s).")


if __name__ == "__main__":
    main()
