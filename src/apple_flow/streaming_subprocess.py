from __future__ import annotations

import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

_STREAM_DONE = object()


@dataclass(frozen=True)
class StreamingCapture:
    stdout: str
    stderr: str
    returncode: int


def capture_subprocess_streams(
    proc: subprocess.Popen[str],
    *,
    timeout: float,
    on_stdout_line: Callable[[str], None] | None = None,
    stdin_text: str | None = None,
) -> StreamingCapture:
    """Capture subprocess stdout/stderr concurrently while enforcing wall timeout.

    Timeout is measured from function start and enforced regardless of whether
    the process is still yielding new output.
    """
    stdout_q: queue.Queue[str | object] = queue.Queue()
    stderr_q: queue.Queue[str | object] = queue.Queue()

    def _reader(stream: object | None, out_q: queue.Queue[str | object]) -> None:
        if stream is None:
            out_q.put(_STREAM_DONE)
            return
        try:
            try:
                iterator = iter(stream)  # type: ignore[arg-type]
            except TypeError:
                iterator = None
            if iterator is not None:
                for line in iterator:
                    out_q.put(line)
            else:
                read = getattr(stream, "read", None)
                if callable(read):
                    chunk = read()
                    if isinstance(chunk, str) and chunk:
                        out_q.put(chunk)
        finally:
            out_q.put(_STREAM_DONE)

    def _writer(stream: object | None, text: str) -> None:
        if stream is None:
            return
        try:
            stream.write(text)  # type: ignore[attr-defined]
            stream.close()  # type: ignore[attr-defined]
        except Exception:
            return

    threading.Thread(target=_reader, args=(proc.stdout, stdout_q), daemon=True).start()
    threading.Thread(target=_reader, args=(proc.stderr, stderr_q), daemon=True).start()
    if stdin_text is not None:
        threading.Thread(target=_writer, args=(proc.stdin, stdin_text), daemon=True).start()

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stdout_done = proc.stdout is None
    stderr_done = proc.stderr is None
    deadline = time.monotonic() + timeout if timeout and timeout > 0 else None

    def _normalize_returncode(polled: object, fallback: object) -> int:
        for candidate in (polled, fallback):
            if isinstance(candidate, bool):
                return int(candidate)
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str):
                try:
                    return int(candidate)
                except ValueError:
                    continue
        return 0

    while True:
        while True:
            try:
                chunk = stdout_q.get_nowait()
            except queue.Empty:
                break
            if chunk is _STREAM_DONE:
                stdout_done = True
                continue
            line = str(chunk)
            stdout_lines.append(line)
            if on_stdout_line:
                on_stdout_line(line)

        while True:
            try:
                chunk = stderr_q.get_nowait()
            except queue.Empty:
                break
            if chunk is _STREAM_DONE:
                stderr_done = True
                continue
            stderr_lines.append(str(chunk))

        polled = proc.poll()
        if polled is not None and stdout_done and stderr_done:
            return StreamingCapture(
                stdout="".join(stdout_lines),
                stderr="".join(stderr_lines),
                returncode=_normalize_returncode(polled, getattr(proc, "returncode", None)),
            )

        if deadline is not None and time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(proc.args, timeout)

        time.sleep(0.05)
