from __future__ import annotations

import csv
import json

from apple_flow.csv_audit import CSV_COLUMNS, CsvAuditLogger


def test_csv_audit_writes_header_once_and_appends(tmp_path):
    csv_path = tmp_path / "audit" / "events.csv"
    logger = CsvAuditLogger(csv_path)

    logger.append_event(
        {
            "created_at": "2026-03-04T10:00:00+00:00",
            "event_id": "evt_1",
            "run_id": "run_1",
            "step": "executor",
            "event_type": "execution_started",
            "payload_json": json.dumps({"a": 1}),
        }
    )
    logger.append_event(
        {
            "created_at": "2026-03-04T10:01:00+00:00",
            "event_id": "evt_2",
            "run_id": "run_1",
            "step": "executor",
            "event_type": "execution_completed",
            "payload_json": json.dumps({"b": 2}),
        }
    )

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    assert rows[0]["event_id"] == "evt_1"
    assert rows[1]["event_id"] == "evt_2"
    assert rows[0]["schema_version"] == "1"
    assert set(rows[0].keys()) == set(CSV_COLUMNS)


def test_csv_audit_escapes_special_characters(tmp_path):
    csv_path = tmp_path / "events.csv"
    logger = CsvAuditLogger(csv_path)

    snippet = 'hello, "world"\nline2'
    logger.append_event(
        {
            "created_at": "2026-03-04T10:00:00+00:00",
            "event_id": "evt_1",
            "run_id": "run_1",
            "step": "executor",
            "event_type": "progress",
            "snippet": snippet,
            "payload_json": json.dumps({"snippet": snippet}),
        }
    )

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]["snippet"] == snippet
    payload = json.loads(rows[0]["payload_json"])
    assert payload["snippet"] == snippet
