"""Opt-in live Numbers smoke tests for multi-sheet workbook flows.

Run only when APPLE_FLOW_NUMBERS_WORKBOOK_SMOKE=1 is set.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from apple_flow.apple_tools import (
    numbers_add_sheet,
    numbers_append_rows,
    numbers_create_workbook,
    numbers_style_apply,
)

NUMBERS_APP_CANDIDATES = (
    'application id "com.apple.Numbers"',
    'application id "com.apple.iWork.Numbers"',
    'application "/Applications/Numbers Creator Studio.app"',
    'application "Numbers Creator Studio"',
    'application "Numbers"',
)

if os.getenv("APPLE_FLOW_NUMBERS_WORKBOOK_SMOKE") != "1":
    pytest.skip("set APPLE_FLOW_NUMBERS_WORKBOOK_SMOKE=1 to run workbook smoke tests", allow_module_level=True)


def _detect_numbers_app_target() -> str | None:
    for target in NUMBERS_APP_CANDIDATES:
        result = subprocess.run(
            ["osascript", "-e", f"tell {target} to count of documents"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return target
    return None


NUMBERS_APP = _detect_numbers_app_target()
if not NUMBERS_APP:
    pytest.skip("Apple Numbers AppleScript automation unavailable in this session", allow_module_level=True)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _run_osascript(script: str, timeout: float = 90.0) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _sheet_names(path: Path) -> list[str]:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set namesOut to {{}}
        repeat with s in sheets of d
            set end of namesOut to (name of s as text)
        end repeat
        close d saving no
        set AppleScript's text item delimiters to character id 9
        return namesOut as text
    end tell
    '''
    raw = _run_osascript(script)
    return [s for s in raw.split("\t") if s]


def _row_count(path: Path, sheet_name: str) -> int:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set s to first sheet of d whose name is "{_esc(sheet_name)}"
        set t to first table of s
        set c to count of rows of t
        close d saving no
        return c as text
    end tell
    '''
    return int(_run_osascript(script))


def _make_path() -> Path:
    root = Path(tempfile.mkdtemp(prefix="appleflow_numbers_workbook.", dir="/tmp"))
    return root / "workbook-smoke.numbers"


def test_create_workbook_multi_sheet():
    path = _make_path()
    result = numbers_create_workbook(
        str(path),
        {
            "sheets": [
                {
                    "sheet_name": "Transactions",
                    "table_name": "Tx",
                    "headers": ["Date", "Item", "Amount"],
                    "rows": [["2026-03-04", "Coffee", 15]],
                },
                {
                    "sheet_name": "Summary",
                    "table_name": "SummaryTable",
                    "headers": ["Metric", "Value"],
                    "rows": [["Total", 15], ["Count", 1]],
                },
                {
                    "sheet_name": "Notes",
                    "headers": ["Date", "Note"],
                    "rows": [],
                },
            ]
        },
        overwrite=True,
    )

    assert result["ok"] is True
    assert result["sheets_created"] == 3
    assert result["rows_inserted_total"] == 3
    assert path.exists()
    assert _sheet_names(path) == ["Transactions", "Summary", "Notes"]


def test_add_sheet_then_append_and_style():
    path = _make_path()
    created = numbers_create_workbook(
        str(path),
        {
            "sheets": [
                {
                    "sheet_name": "Transactions",
                    "table_name": "Tx",
                    "headers": ["Date", "Item", "Amount"],
                    "rows": [["2026-03-04", "Coffee", 15]],
                }
            ]
        },
        overwrite=True,
    )
    assert created["ok"] is True

    added = numbers_add_sheet(
        str(path),
        {
            "sheet_name": "Dashboard",
            "table_name": "DashboardTable",
            "headers": ["Metric", "Value"],
            "rows": [["Total", 15]],
        },
    )
    assert added["ok"] is True

    appended = numbers_append_rows(
        str(path),
        [["Count", 1], ["Average", 15]],
        sheet_name="Dashboard",
        table_name="DashboardTable",
    )
    assert appended["ok"] is True

    styled = numbers_style_apply(
        str(path),
        target={"scope": "range", "start_row": 2, "end_row": 4, "start_column": 1, "end_column": 2},
        style={"font_size": 13, "alignment": "center"},
        sheet_name="Dashboard",
        table_name="DashboardTable",
    )
    assert styled["ok"] is True
    assert styled["cells_touched"] == 6
    assert _row_count(path, "Dashboard") >= 4
