from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


KNOWN_GATEWAYS = ("mail", "reminders", "notes", "calendar")


def gateway_health_state_key(gateway: str) -> str:
    return f"gateway_health_{gateway}"


def gateway_health_payload(
    *,
    healthy: bool,
    last_success_at: str = "",
    last_failure_at: str = "",
    last_failure_reason: str = "",
) -> str:
    return json.dumps(
        {
            "healthy": healthy,
            "last_success_at": last_success_at,
            "last_failure_at": last_failure_at,
            "last_failure_reason": last_failure_reason,
        }
    )


def read_gateway_health(store: Any, gateway: str) -> dict[str, Any] | None:
    if not hasattr(store, "get_state"):
        return None
    raw = store.get_state(gateway_health_state_key(gateway))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def read_all_gateway_health(store: Any) -> dict[str, dict[str, Any]]:
    return {
        gateway: state
        for gateway in KNOWN_GATEWAYS
        if (state := read_gateway_health(store, gateway)) is not None
    }


def summarize_gateway_health_lines(store: Any) -> list[str]:
    lines: list[str] = []
    for gateway, state in read_all_gateway_health(store).items():
        label = gateway.capitalize()
        if state.get("healthy", True):
            line = f"{label}: OK"
            if state.get("last_success_at"):
                line += f" | last success {state['last_success_at']}"
        else:
            line = f"{label}: DEGRADED"
            if state.get("last_failure_reason"):
                line += f" | {state['last_failure_reason']}"
            if state.get("last_failure_at"):
                line += f" | last failure {state['last_failure_at']}"
        lines.append(line)
    return lines


def now_utc_iso() -> str:
    return datetime.now(UTC).isoformat()
