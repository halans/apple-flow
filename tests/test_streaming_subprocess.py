from __future__ import annotations

import subprocess

import pytest

from apple_flow.streaming_subprocess import capture_subprocess_streams


class _FakeProc:
    def __init__(self, *, stdout: object, stderr: object, poll_values: list[int | None]):
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = None
        self.args = ["fake-cmd"]
        self._poll_values = list(poll_values)
        self._poll_index = 0

    def poll(self) -> int | None:
        if not self._poll_values:
            return None
        idx = min(self._poll_index, len(self._poll_values) - 1)
        self._poll_index += 1
        return self._poll_values[idx]


def test_capture_subprocess_streams_collects_output_and_progress():
    proc = _FakeProc(
        stdout=iter(["line 1\n", "line 2\n"]),
        stderr=iter(["warn 1\n"]),
        poll_values=[None, 0, 0],
    )
    progress: list[str] = []

    result = capture_subprocess_streams(
        proc, timeout=1.0, on_stdout_line=progress.append
    )

    assert result.returncode == 0
    assert result.stdout == "line 1\nline 2\n"
    assert result.stderr == "warn 1\n"
    assert progress == ["line 1\n", "line 2\n"]


def test_capture_subprocess_streams_enforces_wall_clock_timeout():
    proc = _FakeProc(
        stdout=iter(()),
        stderr=iter(()),
        poll_values=[None],
    )

    with pytest.raises(subprocess.TimeoutExpired):
        capture_subprocess_streams(proc, timeout=0.05)
