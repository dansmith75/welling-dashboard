#!/usr/bin/env python3
"""Create an unlocked local snapshot of the Welling master workbook via Excel.

The master workbook may be open on another device through OneDrive. Excel can
normally co-author/open that file even when direct ZIP readers such as openpyxl
cannot. This helper asks Excel itself to open the master and SaveCopyAs a local
snapshot for the dashboard exporters.
"""
from __future__ import annotations

import sys
from pathlib import Path


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
    app = None
    book = None
    try:
        app = xw.App(visible=False, add_book=False)
        app.display_alerts = False
        app.screen_updating = False
        book = app.books.open(str(master), update_links=False, read_only=True)

        # Windows Excel exposes SaveCopyAs directly through COM. It produces a
        # normal standalone XLSX that openpyxl can read without touching the
        # live OneDrive workbook again.
        try:
            book.api.SaveCopyAs(str(snapshot))
        except Exception:
            # Fallback for environments where SaveCopyAs is not exposed by the
            # xlwings backend: save a temporary workbook copy under the target
            # path. The source was opened read-only, so the master is untouched.
            book.api.SaveAs(str(snapshot))

        if not snapshot.exists() or snapshot.stat().st_size == 0:
            raise RuntimeError("Excel did not create the snapshot file")

        print(f"SNAPSHOT_CREATED={snapshot}")
    finally:
        if book is not None:
            try:
                book.close()
            except Exception:
                pass
        if app is not None:
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
