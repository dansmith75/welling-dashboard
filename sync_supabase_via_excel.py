#!/usr/bin/env python3
"""Run the Supabase→Excel reconciliation against the live workbook.

If the workbook is already open in Excel on this PC, attach to that exact book
instead of trying to open a second copy. Otherwise open it in a temporary hidden
Excel instance. User-open workbooks are never closed by this helper.

Completed Matchday sessions are reconciled authoritatively: corrections in the
central Matchday record overwrite the corresponding Excel match stats and audit
rows instead of being skipped or incremented twice.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import sync_supabase_to_excel as core
from matchday_authoritative_excel import import_matchday_authoritative


def same_path(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except Exception:
        return False


def find_open_book(xw, workbook_path: Path):
    for app in list(xw.apps):
        try:
            for book in app.books:
                try:
                    if same_path(book.fullname, workbook_path):
                        return app, book
                except Exception:
                    continue
        except Exception:
            continue
    return None, None


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python sync_supabase_via_excel.py /path/to/workbook.xlsx")

    workbook_path = Path(sys.argv[1]).expanduser().resolve()
    if not workbook_path.exists():
        raise FileNotFoundError(workbook_path)

    try:
        import xlwings as xw
    except ImportError as exc:
        raise RuntimeError("xlwings is not installed. Run: python -m pip install xlwings") from exc

    app, book = find_open_book(xw, workbook_path)
    owns_app = False
    owns_book = False

    try:
        if book is not None:
            print("Using workbook already open in Excel on this PC.")
        else:
            app = xw.App(visible=False, add_book=False)
            owns_app = True
            app.display_alerts = False
            app.screen_updating = False
            book = app.books.open(str(workbook_path), update_links=False, read_only=False)
            owns_book = True

        attendance_rows = core.import_attendance(book)
        attendance_views = core.refresh_wide_attendance_sheets(book)
        matchday_sessions, matchday_rows_added, warnings = import_matchday_authoritative(book)

        # Save through Excel whether the book was already open or opened here.
        book.save()

        print("SUPABASE_SYNC_SUMMARY=" + json.dumps({
            "attendanceRows": attendance_rows,
            "matchAttendanceRows": attendance_views.get("matchRows", 0),
            "trainingAttendanceRows": attendance_views.get("trainingRows", 0),
            "matchdaySessions": matchday_sessions,
            "matchdayRows": matchday_rows_added,
            "warnings": warnings,
        }, ensure_ascii=False))
    finally:
        if owns_book and book is not None:
            try:
                book.close()
            except Exception:
                pass
        if owns_app and app is not None:
            try:
                app.quit()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"SUPABASE SYNC FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
