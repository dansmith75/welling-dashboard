"""Apply the current FA Full-Time fixture schedule after each Excel export."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> None:
    matches_path = DATA / "matches.json"
    official_path = DATA / "official-fixtures.json"
    matches = json.loads(matches_path.read_text(encoding="utf-8"))
    official = json.loads(official_path.read_text(encoding="utf-8"))
    cutoff = min(row["date"] for row in official)
    existing = {(row.get("date"), row.get("opposition")): row for row in matches}
    historical = [row for row in matches if str(row.get("date") or "") < cutoff]
    reconciled = []
    for fixture in official:
        row = dict(fixture)
        prior = existing.get((fixture.get("date"), fixture.get("opposition")), {})
        for key in ("goalsFor", "goalsAgainst", "result"):
            if prior.get(key) not in (None, ""):
                row[key] = prior[key]
        reconciled.append(row)
    matches_path.write_text(json.dumps(historical + reconciled, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"- Applied {len(official)} official Full-Time fixture(s).")


if __name__ == "__main__":
    main()
