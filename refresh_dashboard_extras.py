#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

LINK_HEADERS = ["Category", "Name", "URL", "Description", "Active", "Sort Order"]
LEAGUE_HEADERS = ["Position", "Team", "P", "W", "D", "L", "GF", "GA", "GD", "Pts"]
FA_LEAGUE_TABLE_URL = "https://fulltime.thefa.com/table.html?league=3117271&selectedSeason=964418083&selectedDivision=387107891&selectedCompetition=0&selectedFixtureGroupKey=1_822238577"
FA_LEAGUE_HOME_URL = "http://fulltime.thefa.com/index.html?league=3117271&selectedCompetition=0&selectedDivision=387107891&selectedFixtureGroupKey=1_822238577&selectedSeason=964418083"
FA_TEXT_PROXY_URL = "https://r.jina.ai/" + FA_LEAGUE_HOME_URL.replace("&", "%26")
LIVE_FETCH_TIMEOUT = 8
TEXT_PROXY_TIMEOUT = 12

FULLTIME_API_URLS = [
    "https://faapi.jwhsolutions.co.uk/api/League/822238577",
    "https://faapi.jwhsolutions.co.uk/api/League/822238577/season/964418083",
]


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.table = []
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in {"th", "td"}:
            self.cell = []
        elif self.depth == 1 and tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data):
        if self.depth == 1 and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.depth == 1 and tag in {"th", "td"} and self.cell is not None:
            text = " ".join("".join(self.cell).split())
            if self.row is not None:
                self.row.append(html.unescape(text))
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            if any(str(v).strip() for v in self.row):
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            if self.depth == 1 and self.table:
                self.tables.append(self.table)
                self.table = None
            self.depth -= 1


def table_rows(table) -> list[dict[str, Any]]:
    values = table.range.value
    if not values:
        return []
    if not isinstance(values[0], list):
        values = [values]
    headers = [str(v or "").strip() for v in values[0]]
    return [
        {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        for row in values[1:]
        if row and any(v not in (None, "") for v in row)
    ]


def rewrite_table(sheet, table, headers, rows):
    r, c = table.range.row, table.range.column
    end_col = c + len(headers) - 1
    end_row = r + max(1, len(rows))
    table.resize(sheet.range((r, c), (end_row, end_col)))
    sheet.range((r, c), (r, end_col)).value = [headers]
    if rows:
        matrix = [[row.get(h, "") for h in headers] for row in rows]
        sheet.range((r + 1, c), (r + len(rows), end_col)).value = matrix
    else:
        sheet.range((r + 1, c), (r + 1, end_col)).clear_contents()


def ensure_table(book, sheet_name, table_name, headers):
    names = [s.name for s in book.sheets]
    sheet = book.sheets[sheet_name] if sheet_name in names else book.sheets.add(sheet_name, after=book.sheets[-1])
    try:
        table = sheet.tables[table_name]
    except Exception:
        candidates = list(sheet.tables)
        if len(candidates) == 1:
            table = candidates[0]
        else:
            sheet.range("A1").value = [headers]
            sheet.range((2, 1), (2, len(headers))).clear_contents()
            table = sheet.tables.add(sheet.range((1, 1), (2, len(headers))), name=table_name)
            try:
                table.table_style = "TableStyleMedium2"
            except Exception:
                pass
    if [str(v or "").strip() for v in table.range.rows[0].value] != headers:
        rewrite_table(sheet, table, headers, table_rows(table))
    return sheet, table


def truthy(value):
    return str(value or "").strip().lower() not in {"no", "n", "false", "0", "inactive", "off"}


def number(value):
    if value in (None, ""):
        return None
    try:
        f = float(str(value).strip())
        return int(f) if f.is_integer() else f
    except Exception:
        return value


def clean(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=LIVE_FETCH_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def find_dict_lists(value):
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            yield value
        for item in value:
            yield from find_dict_lists(item)
    elif isinstance(value, dict):
        for child in value.values():
            yield from find_dict_lists(child)


def pick(item, names, default=None):
    data = {clean(k): v for k, v in item.items()}
    for name in names:
        if name in data:
            return data[name]
    return default


def normalise_api(payload):
    aliases = {
        "Position": {"position", "pos", "place", "rank", "ranking"},
        "Team": {"team", "teamname", "club", "clubname", "name"},
        "P": {"p", "pl", "played", "gamesplayed", "matchesplayed"},
        "W": {"w", "won", "wins"}, "D": {"d", "drawn", "draws"}, "L": {"l", "lost", "losses"},
        "GF": {"gf", "goalsfor", "for"}, "GA": {"ga", "goalsagainst", "against"},
        "GD": {"gd", "goaldifference", "difference", "diff"}, "Pts": {"pts", "points", "point"},
    }
    for items in find_dict_lists(payload):
        rows = []
        for item in items:
            team = str(pick(item, aliases["Team"], "") or "").strip()
            played = pick(item, aliases["P"], None)
            points = pick(item, aliases["Pts"], None)
            if not team or played is None or points is None:
                continue
            rows.append({
                "Position": number(pick(item, aliases["Position"], len(rows) + 1)) or len(rows) + 1,
                "Team": team,
                "P": number(played) or 0,
                "W": number(pick(item, aliases["W"], 0)) or 0,
                "D": number(pick(item, aliases["D"], 0)) or 0,
                "L": number(pick(item, aliases["L"], 0)) or 0,
                "GF": number(pick(item, aliases["GF"], 0)) or 0,
                "GA": number(pick(item, aliases["GA"], 0)) or 0,
                "GD": number(pick(item, aliases["GD"], 0)) or 0,
                "Pts": number(points) or 0,
            })
        if len(rows) >= 2:
            return rows
    raise RuntimeError("response contained no identifiable standings")


def fetch_api_league():
    failures = []
    for url in FULLTIME_API_URLS:
        try:
            return normalise_api(fetch_json(url)), url
        except Exception as exc:
            failures.append(f"{url} -> {exc}")
    raise RuntimeError("; ".join(failures))


def fetch_fa_html():
    req = urllib.request.Request(FA_LEAGUE_TABLE_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=LIVE_FETCH_TIMEOUT) as response:
        markup = response.read().decode("utf-8", errors="replace")
    parser = TableParser(); parser.feed(markup)
    aliases = {
        "Position": {"pos", "position", "place"}, "Team": {"team", "club"},
        "P": {"p", "pl", "played"}, "W": {"w", "won"}, "D": {"d", "drawn"}, "L": {"l", "lost"},
        "GF": {"gf", "goalsfor", "f", "for"}, "GA": {"ga", "goalsagainst", "a", "against"},
        "GD": {"gd", "goaldifference", "diff"}, "Pts": {"pts", "points"},
    }
    for table in parser.tables:
        for hidx, headers in enumerate(table[:5]):
            indices = {k: next((i for i, h in enumerate(headers) if clean(h) in vals), None) for k, vals in aliases.items()}
            if any(indices[k] is None for k in ["Team", "P", "W", "D", "L", "Pts"]):
                continue
            rows = []
            for raw in table[hidx + 1:]:
                ti = indices["Team"]
                if ti is None or ti >= len(raw):
                    continue
                team = str(raw[ti] or "").strip()
                if not team:
                    continue
                def cell(key):
                    i = indices[key]
                    return raw[i] if i is not None and i < len(raw) else ""
                rows.append({
                    "Position": number(cell("Position")) or len(rows)+1,
                    "Team": team,
                    "P": number(cell("P")) or 0,
                    "W": number(cell("W")) or 0,
                    "D": number(cell("D")) or 0,
                    "L": number(cell("L")) or 0,
                    "GF": number(cell("GF")) or 0,
                    "GA": number(cell("GA")) or 0,
                    "GD": number(cell("GD")) or 0,
                    "Pts": number(cell("Pts")) or 0,
                })
            if len(rows) >= 2:
                return rows
    raise RuntimeError("could not identify standings table")


def fetch_fa_markdown():
    """Read the public Full-Time page through a text renderer when FA blocks scripts."""
    req = urllib.request.Request(FA_TEXT_PROXY_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"})
    with urllib.request.urlopen(req, timeout=TEXT_PROXY_TIMEOUT) as response:
        text = response.read().decode("utf-8", errors="replace")
    marker = "## League Table"
    # Full-Time and text proxies occasionally change or omit this heading.
    # Scan the whole response when that happens; the row parser below only
    # accepts a ten-column table whose first cell is a numeric position.
    section = text.split(marker, 1)[1] if marker in text else text
    rows = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 10 or clean(cells[0]) in {"pos", "position", ""} or set(cells[0]) == {"-"}:
            continue
        try:
            position = int(cells[0])
        except ValueError:
            continue
        team = re.sub(r"^\[([^]]+)\]\([^)]*\)$", r"\1", cells[1]).strip()
        rows.append({
            "Position": position, "Team": team,
            "P": number(cells[2]) or 0, "W": number(cells[3]) or 0,
            "D": number(cells[4]) or 0, "L": number(cells[5]) or 0,
            "GF": number(cells[6]) or 0, "GA": number(cells[7]) or 0,
            "GD": number(cells[8]) or 0, "Pts": number(cells[9]) or 0,
        })
    if len(rows) < 2:
        raise RuntimeError("proxied Full-Time page contained no standings")
    return rows


def league_json(rows):
    out = []
    for row in rows:
        team = str(row.get("Team") or "").strip()
        if team:
            out.append({
                "position": number(row.get("Position")),
                "team": team,
                "played": number(row.get("P")) or 0,
                "won": number(row.get("W")) or 0,
                "drawn": number(row.get("D")) or 0,
                "lost": number(row.get("L")) or 0,
                "goalsFor": number(row.get("GF")) or 0,
                "goalsAgainst": number(row.get("GA")) or 0,
                "goalDifference": number(row.get("GD")) or 0,
                "points": number(row.get("Pts")) or 0,
            })
    out.sort(key=lambda r: (r["position"] if isinstance(r["position"], (int, float)) else 999, r["team"].lower()))
    return out


def published_rows(path: Path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict) or not str(item.get("team") or "").strip():
            continue
        rows.append({
            "Position": item.get("position"),
            "Team": item.get("team"),
            "P": item.get("played", 0),
            "W": item.get("won", 0),
            "D": item.get("drawn", 0),
            "L": item.get("lost", 0),
            "GF": item.get("goalsFor", 0),
            "GA": item.get("goalsAgainst", 0),
            "GD": item.get("goalDifference", 0),
            "Pts": item.get("points", 0),
        })
    return rows


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python refresh_dashboard_extras.py /path/to/workbook.xlsx")

    workbook = Path(sys.argv[1]).expanduser().resolve()
    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    league_json_path = data_dir / "league-table.json"
    last_published_rows = published_rows(league_json_path)

    import xlwings as xw
    app = xw.App(visible=False, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    book = None
    try:
        book = app.books.open(str(workbook), update_links=False, read_only=False)
        links_sheet, links_table = ensure_table(book, "Web Links", "WebLinks", LINK_HEADERS)
        league_sheet, league_table = ensure_table(book, "League Table", "LeagueTable", LEAGUE_HEADERS)

        try:
            links_sheet.range("A:F").column_width = 18
            links_sheet.range("C:C").column_width = 42
            links_sheet.range("D:D").column_width = 34
            league_sheet.range("A:J").column_width = 10
            league_sheet.range("B:B").column_width = 28
        except Exception:
            pass

        links = []
        for row in table_rows(links_table):
            url = str(row.get("URL") or "").strip()
            name = str(row.get("Name") or "").strip()
            if url and name and truthy(row.get("Active")):
                links.append({
                    "category": str(row.get("Category") or "Useful Links").strip() or "Useful Links",
                    "name": name,
                    "url": url,
                    "description": str(row.get("Description") or "").strip(),
                    "sortOrder": number(row.get("Sort Order")) or 999,
                })
        links.sort(key=lambda r: (r["category"].lower(), r["sortOrder"], r["name"].lower()))

        excel_rows = table_rows(league_table)
        live_rows = None
        source = None

        try:
            live_rows = fetch_fa_markdown()
            source = "FA Full-Time public page"
            print(f"League table refreshed from FA Full-Time: {len(live_rows)} teams")
        except Exception as proxy_exc:
            print(f"WARNING: Full-Time text refresh failed: {proxy_exc}")
            try:
                live_rows, used_url = fetch_api_league()
                source = "FullTime API"
                print(f"League table refreshed via FullTime API: {len(live_rows)} teams")
                print(f"League source: {used_url}")
            except Exception as api_exc:
                print(f"WARNING: FullTime API refresh failed: {api_exc}")
                try:
                    live_rows = fetch_fa_html()
                    source = "FA Full-Time page"
                    print(f"League table refreshed directly from FA Full-Time: {len(live_rows)} teams")
                except Exception as fa_exc:
                    print(f"WARNING: Direct FA Full-Time refresh failed: {fa_exc}")

        if live_rows:
            chosen_rows = live_rows
            rewrite_table(league_sheet, league_table, LEAGUE_HEADERS, chosen_rows)
        elif excel_rows:
            chosen_rows = excel_rows
            source = "Excel League Table"
            print(f"Using Excel League Table fallback: {len(chosen_rows)} teams")
        elif last_published_rows:
            chosen_rows = last_published_rows
            source = "last published league table"
            rewrite_table(league_sheet, league_table, LEAGUE_HEADERS, chosen_rows)
            print(f"Using last published league table fallback: {len(chosen_rows)} teams")
            print("League Table sheet has been repopulated from the last known-good published table.")
        else:
            chosen_rows = []
            source = "no available league data"
            print("WARNING: No live, Excel, or previously published league table is available.")
            print("Existing league-table.json will not be replaced with an empty table.")

        book.save()

        (data_dir / "links.json").write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")
        if chosen_rows:
            league = league_json(chosen_rows)
            league_json_path.write_text(json.dumps(league, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Dashboard extras refreshed: {len(links)} web links, {len(league)} league rows ({source})")
        else:
            print(f"Dashboard extras refreshed: {len(links)} web links; league table preserved ({source})")
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
