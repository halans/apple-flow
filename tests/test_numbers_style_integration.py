"""Opt-in live Numbers smoke tests for styling.

Run only when APPLE_FLOW_NUMBERS_STYLE_SMOKE=1 is set.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from apple_flow.apple_tools import numbers_append_rows, numbers_create, numbers_style_apply

NUMBERS_APP_CANDIDATES = (
    'application id "com.apple.Numbers"',
    'application id "com.apple.iWork.Numbers"',
    'application "/Applications/Numbers Creator Studio.app"',
    'application "Numbers Creator Studio"',
    'application "Numbers"',
)

if os.getenv("APPLE_FLOW_NUMBERS_STYLE_SMOKE") != "1":
    pytest.skip("set APPLE_FLOW_NUMBERS_STYLE_SMOKE=1 to run live Numbers style tests", allow_module_level=True)


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


def _make_doc() -> Path:
    root = Path(tempfile.mkdtemp(prefix="appleflow_numbers_style.", dir="/tmp"))
    path = root / "style-smoke.numbers"
    created = numbers_create(str(path), headers=["A", "B", "C"], overwrite=True)
    assert created == str(path)
    inserted = numbers_append_rows(str(path), [["hello", 19.99, "x"], ["world", 21.50, "y"]])
    assert inserted["ok"] is True
    return path


def _read_style_snapshot(path: Path) -> dict[str, str]:
    script = f'''
    tell {NUMBERS_APP}
        set d to open POSIX file "{_esc(str(path))}"
        set t to first table of first sheet of d
        tell t
            set fs to font size of cell 1 of row 2
            set al to alignment of cell 1 of row 2
            set tw to text wrap of cell 1 of row 2
            set fm to format of cell 2 of row 2
            set rh to height of row 2
            set cw to width of column 1
        end tell
        close d saving no
        return (fs as text) & character id 9 & (al as text) & character id 9 & (tw as text) & character id 9 & (fm as text) & character id 9 & (rh as text) & character id 9 & (cw as text)
    end tell
    '''
    raw = _run_osascript(script)
    fs, al, tw, fm, rh, cw = raw.split("\t")
    return {
        "font_size": float(fs),
        "alignment": al.lower(),
        "text_wrap": tw.lower(),
        "format": fm.lower(),
        "row_height": float(rh),
        "column_width": float(cw),
    }


def test_style_apply_range_updates_properties():
    path = _make_doc()
    result = numbers_style_apply(
        str(path),
        target={"scope": "range", "start_row": 2, "end_row": 3, "start_column": 1, "end_column": 2},
        style={
            "font_size": 14,
            "alignment": "center",
            "text_wrap": True,
            "number_format": "currency",
            "row_height": 34,
            "column_width": 180,
        },
    )

    assert result["ok"] is True
    assert result["cells_touched"] == 4
    assert result["rows_resized"] == 2
    assert result["columns_resized"] == 2

    snapshot = _read_style_snapshot(path)
    assert snapshot["font_size"] == 14.0
    assert snapshot["alignment"] == "center"
    assert snapshot["text_wrap"] == "true"
    assert snapshot["format"] == "currency"
    assert snapshot["row_height"] == 34.0
    assert snapshot["column_width"] == 180.0


def test_style_apply_out_of_bounds_range_errors():
    path = _make_doc()
    result = numbers_style_apply(
        str(path),
        target={"scope": "range", "start_row": 2, "end_row": 100, "start_column": 1, "end_column": 2},
        style={"font_size": 12},
    )
    assert result["ok"] is False
    assert "range row out of bounds" in result["error"]
