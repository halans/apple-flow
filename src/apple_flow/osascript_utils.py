from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass


_TRANSIENT_MARKERS = (
    "Connection Invalid error for service com.apple.hiservices-xpcservice",
    "Error received in message reply handler: Connection invalid",
    "Expected class name but found identifier. (-2741)",
)

_APP_NOT_RUNNING_MARKERS = (
    "Application isn’t running. (-600)",
    "Application isn't running. (-600)",
    "Can’t get application",
    "Can't get application",
)


@dataclass(frozen=True)
class OsaScriptRunResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    attempts: int = 1
    warmed_app: bool = False

    @property
    def detail(self) -> str:
        if self.stderr:
            return self.stderr
        if self.returncode and not self.stdout:
            return f"osascript exit code {self.returncode}"
        return self.stdout


def is_transient_osascript_error(stderr: str) -> bool:
    return any(marker in stderr for marker in _TRANSIENT_MARKERS)


def is_app_not_running_error(stderr: str) -> bool:
    return any(marker in stderr for marker in _APP_NOT_RUNNING_MARKERS)


def _run_command(cmd: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def warm_app(app_name: str, *, timeout: float = 10.0) -> bool:
    if not app_name:
        return False
    try:
        result = _run_command(["open", "-a", app_name], timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if result.returncode != 0:
        return False
    time.sleep(1.0)
    return True


def run_osascript_with_recovery(
    script: str,
    *,
    app_name: str = "",
    timeout: float = 30.0,
    max_attempts: int = 3,
    backoff_seconds: float = 0.5,
    warm_on_not_running: bool = True,
) -> OsaScriptRunResult:
    attempts = max(1, int(max_attempts))
    warmed = False
    last_stderr = ""
    last_returncode = 0

    for attempt in range(1, attempts + 1):
        try:
            result = _run_command(["osascript", "-e", script], timeout=timeout)
        except subprocess.TimeoutExpired:
            last_stderr = "timed out"
            last_returncode = -1
            if attempt < attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            return OsaScriptRunResult(
                ok=False,
                stderr=last_stderr,
                returncode=last_returncode,
                attempts=attempt,
                warmed_app=warmed,
            )
        except FileNotFoundError:
            return OsaScriptRunResult(
                ok=False,
                stderr="osascript not found (requires macOS)",
                returncode=-1,
                attempts=attempt,
                warmed_app=warmed,
            )
        except OSError as exc:
            return OsaScriptRunResult(
                ok=False,
                stderr=f"os error: {exc}",
                returncode=-1,
                attempts=attempt,
                warmed_app=warmed,
            )

        stdout = (result.stdout or "").strip("\r\n")
        stderr = (result.stderr or "").strip()
        if result.returncode == 0:
            return OsaScriptRunResult(
                ok=True,
                stdout=stdout,
                stderr=stderr,
                returncode=0,
                attempts=attempt,
                warmed_app=warmed,
            )

        last_stderr = stderr or f"osascript exit code {result.returncode}"
        last_returncode = result.returncode

        if warm_on_not_running and app_name and is_app_not_running_error(last_stderr) and not warmed:
            warmed = warm_app(app_name)
            if warmed and attempt < attempts:
                continue

        if is_transient_osascript_error(last_stderr) and attempt < attempts:
            time.sleep(backoff_seconds * attempt)
            continue

        return OsaScriptRunResult(
            ok=False,
            stdout=stdout,
            stderr=last_stderr,
            returncode=last_returncode,
            attempts=attempt,
            warmed_app=warmed,
        )

    return OsaScriptRunResult(
        ok=False,
        stderr=last_stderr,
        returncode=last_returncode,
        attempts=attempts,
        warmed_app=warmed,
    )
