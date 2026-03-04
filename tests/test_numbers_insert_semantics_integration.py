"""Opt-in live Numbers smoke tests for row insertion semantics.

Run only when APPLE_FLOW_NUMBERS_SMOKE=1 is set.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from apple_flow.apple_tools import numbers_append_rows, numbers_create

NUMBERS_APP_CANDIDATES = (
    'application id "com.apple.Numbers"',
    'application id "com.apple.iWork.Numbers"',
    'application "/Applications/Numbers Creator Studio.app"',
    'application "Numbers Creator Studio"',
    'application "Numbers"',
)

if os.getenv("APPLE_FLOW_NUMBERS_SMOKE") != "1":
    pytest.skip("set APPLE_FLOW_NUMBERS_SMOKE=1 to run live Numbers smoke tests", allow_module_level=True)


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
    pytest.skip(
        "Apple Numbers AppleScript automation unavailable in this session",
        allow_module_level=True,
    )


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _run_osascript(script: str, timeout: float = 60.0) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _row_count(path: Path) -> int:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set t to first table of first sheet of d
        set r to count of rows of t
        close d saving no
        return r as text
    end tell
    '''
    return int(_run_osascript(script))


def _set_row(path: Path, row_index: int, col1: str, col2: str) -> None:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set t to first table of first sheet of d
        tell t
            set value of cell 1 of row {row_index} to "{_esc(col1)}"
            set value of cell 2 of row {row_index} to "{_esc(col2)}"
        end tell
        save d
        close d saving yes
    end tell
    '''
    _run_osascript(script)


def _read_rows(path: Path, start_row: int, end_row: int) -> list[list[str]]:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set t to first table of first sheet of d
        set outputLines to {{}}
        tell t
            repeat with r from {start_row} to {end_row}
                set c1 to ""
                set c2 to ""
                try
                    set v1 to value of cell 1 of row r
                    if v1 is not missing value then set c1 to v1 as text
                end try
                try
                    set v2 to value of cell 2 of row r
                    if v2 is not missing value then set c2 to v2 as text
                end try
                set end of outputLines to c1 & character id 9 & c2
            end repeat
        end tell
        close d saving no
        set AppleScript's text item delimiters to character id 10
        return outputLines as text
    end tell
    '''
    raw = _run_osascript(script)
    parsed: list[list[str]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) == 1:
            parts.append("")
        parsed.append(parts[:2])
    return parsed


def _create_doc(path: Path) -> None:
    created = numbers_create(str(path), headers=["Item", "Amount"], overwrite=True)
    assert created == str(path)


def _temp_doc(name: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="appleflow_numbers_smoke.", dir="/tmp"))
    return root / name


def test_after_data_fills_top_blank_rows():
    path = _temp_doc("after-data-smoke.numbers")
    _create_doc(path)

    result = numbers_append_rows(
        str(path),
        [["Coffee", 15], ["Burger", 30], ["Water", 2]],
        insert_position="after-data",
    )

    assert result["ok"] is True
    assert result["start_row"] == 2
    assert _read_rows(path, 2, 4) == [["Coffee", "15.0"], ["Burger", "30.0"], ["Water", "2.0"]]


def test_after_headers_inserts_before_existing_data():
    path = _temp_doc("after-headers-smoke.numbers")
    _create_doc(path)
    _set_row(path, 2, "Existing", "99")

    result = numbers_append_rows(
        str(path),
        [["TopInsert", 10]],
        insert_position="after-headers",
    )

    assert result["ok"] is True
    assert result["start_row"] == 2
    assert _read_rows(path, 2, 3) == [["TopInsert", "10.0"], ["Existing", "99.0"]]


def test_at_end_appends_below_current_table_end():
    path = _temp_doc("at-end-smoke.numbers")
    _create_doc(path)

    initial_rows = _row_count(path)
    result = numbers_append_rows(
        str(path),
        [["EndRow", 42]],
        insert_position="at-end",
    )

    assert result["ok"] is True
    assert result["start_row"] == initial_rows + 1
    assert _read_rows(path, initial_rows + 1, initial_rows + 1) == [["EndRow", "42.0"]]
