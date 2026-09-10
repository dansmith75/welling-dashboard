#!/usr/bin/env python3
"""Export player bios while keeping Squad > Strap Line authoritative.

Blank Excel straplines remain blank and are never replaced with generated text.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


STRAPLINES = {
    "goalkeeper": [
        "Professional shot-stopper. Part-time distributor of unsolicited instructions.",
        "Hands like glue. Volume control still under development.",
        "Last line of defence and first to explain whose fault it definitely wasn't.",
    ],
    "defender": [
        "Defends first, asks questions later. Usually after the clearance lands in another postcode.",
        "Built for tackles, headers and insisting it was definitely all ball.",
        "Specialist in making strikers reconsider their afternoon plans.",
        "Keeps things simple: win it, clear it, blame the midfield.",
    ],
    "midfielder": [
        "Runs the engine room. Occasionally remembers to switch the engine off.",
        "Links defence and attack, plus several conversations the referee didn't ask for.",
        "Covers every blade of grass, including a few that aren't technically on the pitch.",
        "Pass, move, repeat. Add unnecessary worldie attempt when confidence permits.",
    ],
    "winger": [
        "One mission: get at the full-back until one of them needs a sit down.",
        "Likes space, pace and a defender facing the wrong direction.",
        "Designed to turn a quiet afternoon for the opposition full-back into admin.",
    ],
    "forward": [
        "Lives for goals. Will also accept assists if absolutely necessary.",
        "Striker: permanently one chance away from claiming he meant it.",
        "Occupies centre-backs, penalty areas and most post-match conversations.",
        "Shoots on sight. Definition of sight may vary.",
    ],
    "utility": [
        "Plays wherever required, which is football's polite way of saying never gets a quiet week.",
        "Position: yes. Job: whatever needs doing.",
        "The tactical Swiss Army knife. Less useful for opening bottles.",
    ],
}

BIOS = {
    "goalkeeper": "Goalkeeper. Responsible for keeping the ball out, organising the defence and making routine saves look slightly more dramatic than necessary.",
    "defender": "Defender. Happy in a duel, happier after a clean sheet, and happiest when somebody else has to chase the ball into the car park.",
    "midfielder": "Midfielder. Expected to win it, keep it, move it and somehow still have enough legs left to do the same thing again two minutes later.",
    "winger": "Wide player. There to stretch the pitch, attack defenders and create the sort of one-v-one situations coaches pretend are completely planned.",
    "forward": "Forward. Paid in chances rather than money, judged almost entirely on what happens inside eighteen yards and always convinced the next one is going in.",
    "utility": "Versatile squad player. Capable of filling several positions and therefore at constant risk of becoming far too useful for their own good.",
}


def text(value: Any) -> str:
    return str(value or "").strip()


def normal(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text(value).lower()).strip()


def position_group(position: str) -> str:
    p = normal(position)
    if any(token in p for token in ("goalkeeper", "keeper", "gk")):
        return "goalkeeper"
    if any(token in p for token in ("wing", "wide")):
        return "winger"
    if any(token in p for token in ("striker", "forward", "centre forward", "center forward", "cf")):
        return "forward"
    if any(token in p for token in ("mid", "cm", "dm", "am")):
        return "midfielder"
    if any(token in p for token in ("back", "def", "cb", "lb", "rb")):
        return "defender"
    return "utility"


def default_strapline(player_id: str, position: str) -> str:
    group = position_group(position)
    choices = STRAPLINES[group]
    seed = sum(ord(ch) for ch in player_id.lower())
    return choices[seed % len(choices)]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python ensure_player_bios.py /path/to/workbook.xlsx")

    workbook = Path(sys.argv[1]).expanduser().resolve()
    if not workbook.exists():
        raise FileNotFoundError(workbook)

    import xlwings as xw

    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    book = None
    try:
        book = app.books.open(str(workbook), update_links=False, read_only=False)
        sheet = book.sheets["Squad"]
        try:
            table = sheet.tables["Squad"]
        except Exception:
            if len(sheet.tables) != 1:
                raise RuntimeError("Squad sheet needs one identifiable player table")
            table = sheet.tables[0]

        headers = [text(v) for v in table.range.rows[0].value]
        header_lookup = {normal(value).replace(" ", ""): index for index, value in enumerate(headers)}

        if "strapline" not in header_lookup:
            new_column = table.api.ListColumns.Add()
            new_column.Name = "Strap Line"
            headers = [text(v) for v in table.range.rows[0].value]
            header_lookup = {normal(value).replace(" ", ""): index for index, value in enumerate(headers)}

        def idx(*names: str) -> int | None:
            for name in names:
                found = header_lookup.get(normal(name).replace(" ", ""))
                if found is not None:
                    return found
            return None

        id_idx = idx("ID")
        name_idx = idx("Display Name", "DisplayName", "Name")
        position_idx = idx("Position")
        strap_idx = idx("Strap Line", "StrapLine")
        if id_idx is None or name_idx is None or strap_idx is None:
            raise RuntimeError("Squad table needs ID, Display Name and Strap Line columns")

        matrix = table.range.value
        if not isinstance(matrix, list):
            matrix = []
        rows = matrix[1:] if matrix else []
        exported = []
        filled = 0

        first_data_row = table.range.row + 1
        first_col = table.range.column

        for offset, row in enumerate(rows):
            if not isinstance(row, list):
                continue
            player_id = text(row[id_idx] if id_idx < len(row) else "")
            display_name = text(row[name_idx] if name_idx < len(row) else "")
            if not player_id or not display_name or player_id.lower() == "total":
                continue

            position = text(row[position_idx] if position_idx is not None and position_idx < len(row) else "")
            strapline = text(row[strap_idx] if strap_idx < len(row) else "")
            group = position_group(position)
            exported.append({
                "id": player_id,
                "displayName": display_name,
                "position": position,
                "strapLine": strapline,
                "bio": BIOS[group],
            })

        book.save()

        destination = Path(__file__).resolve().parent / "data" / "bios.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(exported, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Player bios refreshed: {len(exported)} players, {filled} blank straplines filled")
    finally:
        if book is not None:
            try:
                book.close()
            except Exception:
                pass
        try:
            app.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
