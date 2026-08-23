#!/usr/bin/env python3
"""Create a local snapshot of the Welling master workbook via Excel.

If the workbook is already open in Excel on this PC, reuse that live workbook
and SaveCopyAs from it. Otherwise open it in a temporary hidden Excel instance.
This avoids direct openpyxl access to the OneDrive master and does not close a
workbook the user already had open.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def same_path(a: str | Path, b: str | Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except Exception:
        return False


def find_open_book(xw, master: Path):
    for app in list(xw.apps):
        try:
            for book in app.books:
                try:
                    if same_path(book.fullname, master):
                        return app, book
                except Exception:
                    continue
        except Exception:
            continue
    return None, None


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python create_workbook_snapshot.py MASTER.xlsx SNAPSHOT.xlsx")

    master = Path(sys.argv[1]).expanduser().resolve()
    snapshot = Path(sys.argv[2]).expanduser().resolve()
    if not master.exists():
        raise FileNotFoundError(master)

    try:
        import xlwings as xw
    except ImportError as exc:
        raise RuntimeError("xlwings is not installed. Run: python -m pip install xlwings") from exc

    snapshot.parent.mkdir(parents=True, exist_ok=True)
    app, book = find_open_book(xw, master)
    owns_app = False
    owns_book = False

    try:
        if book is not None:
            print("Creating snapshot from workbook already open in Excel on this PC.")
            book.save()
        else:
            app = xw.App(visible=False, add_book=False)
            owns_app = True
            app.display_alerts = False
            app.screen_updating = False
            book = app.books.open(str(master), update_links=False, read_only=True)
            owns_book = True

        if snapshot.exists():
            try:
                snapshot.unlink()
            except Exception:
                pass

        try:
            book.api.SaveCopyAs(str(snapshot))
        except Exception:
            # SaveCopyAs should be available on Windows Excel. Keep a fallback
            # for other xlwings backends when the source is not a user-open book.
            if not owns_book:
                raise
            book.api.SaveAs(str(snapshot))

        if not snapshot.exists() or snapshot.stat().st_size == 0:
            raise RuntimeError("Excel did not create the snapshot file")

        print(f"SNAPSHOT_CREATED={snapshot}")
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
        print(f"SNAPSHOT FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
