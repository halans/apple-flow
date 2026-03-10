from __future__ import annotations

import subprocess

from apple_flow.osascript_utils import run_osascript_with_recovery


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["osascript", "-e", "test"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_osascript_with_recovery_retries_transient_connection_invalid(monkeypatch):
    calls: list[list[str]] = []
    results = [
        _completed(
            1,
            stderr="Error received in message reply handler: Connection invalid\nConnection Invalid error for service com.apple.hiservices-xpcservice.",
        ),
        _completed(0, stdout="ok\n"),
    ]

    def fake_run(cmd, capture_output, text, timeout, check=False):
        calls.append(cmd)
        return results.pop(0)

    monkeypatch.setattr("apple_flow.osascript_utils.subprocess.run", fake_run)
    monkeypatch.setattr("apple_flow.osascript_utils.time.sleep", lambda _seconds: None)

    result = run_osascript_with_recovery('tell application "Notes" to count of folders', app_name="Notes")

    assert result.ok is True
    assert result.stdout == "ok"
    assert len(calls) == 2


def test_run_osascript_with_recovery_launches_app_when_not_running(monkeypatch):
    calls: list[list[str]] = []
    opened: list[list[str]] = []
    results = [
        _completed(1, stderr='execution error: Calendar got an error: Application isn’t running. (-600)'),
        _completed(0, stdout="ok\n"),
    ]

    def fake_run(cmd, capture_output, text, timeout, check=False):
        calls.append(cmd)
        if cmd[:2] == ["open", "-a"]:
            opened.append(cmd)
            return _completed(0)
        return results.pop(0)

    monkeypatch.setattr("apple_flow.osascript_utils.subprocess.run", fake_run)
    monkeypatch.setattr("apple_flow.osascript_utils.time.sleep", lambda _seconds: None)

    result = run_osascript_with_recovery('tell application "Calendar" to count of calendars', app_name="Calendar")

    assert result.ok is True
    assert result.stdout == "ok"
    assert opened == [["open", "-a", "Calendar"]]
    assert len(calls) == 3
