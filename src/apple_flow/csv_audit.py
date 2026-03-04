from __future__ import annotations

import csv
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("apple_flow.csv_audit")


CSV_SCHEMA_VERSION = "1"
CSV_COLUMNS = [
    "schema_version",
    "created_at",
    "event_id",
    "run_id",
    "step",
    "event_type",
    "channel",
    "sender",
    "workspace",
    "connector",
    "attempt",
    "status",
    "duration_ms",
    "snippet",
    "payload_json",
]


class CsvAuditLogger:
    """Append-only CSV audit writer for structured event analytics."""

    def __init__(self, path: Path, include_headers_if_missing: bool = True):
        self.path = Path(path)
        self.include_headers_if_missing = include_headers_if_missing
        self._lock = threading.Lock()

    def append_event(self, event_row: dict[str, Any]) -> None:
        """Append a single event row in a stable CSV schema."""
        row = {key: "" for key in CSV_COLUMNS}
        for key in CSV_COLUMNS:
            if key in event_row and event_row[key] is not None:
                row[key] = str(event_row[key])
        row["schema_version"] = CSV_SCHEMA_VERSION

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            needs_header = self.include_headers_if_missing and (
                (not self.path.exists()) or self.path.stat().st_size == 0
            )

            try:
                with self.path.open("a", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                    if needs_header:
                        writer.writeheader()
                    writer.writerow(row)
            except Exception as exc:
                logger.warning("Failed to append CSV audit row to %s: %s", self.path, exc)
