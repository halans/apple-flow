"""Tests for native Ollama connector."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

from apple_flow.ollama_connector import OllamaConnector


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, _url, json=None):
        assert json is not None
        if not self._responses:
            raise AssertionError("No fake responses left")
        return self._responses.pop(0)


def _make_mock_proc(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    communicate_side_effect: Exception | None = None,
) -> Mock:
    proc = Mock()
    proc.pid = 12345
    proc.returncode = returncode
    proc.poll = Mock(return_value=returncode)
    proc.communicate = Mock(return_value=(stdout, stderr))
    if communicate_side_effect is not None:
        proc.communicate.side_effect = communicate_side_effect
    return proc


def test_ollama_connector_implements_protocol():
    from apple_flow.protocols import ConnectorProtocol

    connector = OllamaConnector()
    assert isinstance(connector, ConnectorProtocol)


def test_run_turn_success_text_only():
    connector = OllamaConnector(
        base_url="http://127.0.0.1:11434",
        model="qwen3.5:4b",
        inject_tools_context=False,
        auto_pull_model=False,
    )

    fake_client = _FakeClient(
        [
            _FakeResponse(
                200,
                {"message": {"content": "hello from ollama"}},
            )
        ]
    )

    with patch("apple_flow.ollama_connector.httpx.Client", return_value=fake_client):
        response = connector.run_turn("+15551234567", "say hi")

    assert response == "hello from ollama"
    assert "+15551234567" in connector._sender_contexts


def test_chat_missing_model_autopull_retry_success():
    connector = OllamaConnector(auto_pull_model=True, inject_tools_context=False)

    first = _FakeClient([_FakeResponse(404, text="model not found, try pull")])
    second = _FakeClient([_FakeResponse(200, {"message": {"content": "ok"}})])

    with (
        patch("apple_flow.ollama_connector.httpx.Client", side_effect=[first, second]),
        patch.object(connector, "_ensure_model_pulled", return_value=True),
    ):
        result = connector._chat(messages=[{"role": "user", "content": "test"}], allow_tools=False)

    assert isinstance(result, dict)
    assert result["message"]["content"] == "ok"


def test_chat_missing_model_autopull_failure_returns_guidance():
    connector = OllamaConnector(auto_pull_model=True, inject_tools_context=False)
    first = _FakeClient([_FakeResponse(404, text="model not found")])

    with (
        patch("apple_flow.ollama_connector.httpx.Client", return_value=first),
        patch.object(connector, "_ensure_model_pulled", return_value=False),
    ):
        result = connector._chat(messages=[{"role": "user", "content": "test"}], allow_tools=False)

    assert isinstance(result, str)
    assert "ollama pull" in result.lower()


def test_run_turn_tool_loop_executes_shell_command():
    connector = OllamaConnector(
        workspace="/tmp",
        allowed_workspaces=["/tmp"],
        inject_tools_context=False,
    )

    responses = [
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "run_shell_command",
                            "arguments": {"command": "echo hi"},
                        }
                    }
                ],
            }
        },
        {"message": {"content": "done"}},
    ]

    def _fake_chat(*, messages, allow_tools):
        assert allow_tools is True
        return responses.pop(0)

    mock_proc = _make_mock_proc(stdout="hi\n")
    with (
        patch.object(connector, "_chat", side_effect=_fake_chat),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        result = connector.run_turn("+15551234567", "run command", options={"allow_tools": True, "cwd": "/tmp"})

    assert result == "done"
    mock_popen.assert_called_once()


def test_run_turn_tool_loop_blocks_outside_allowed_workspace():
    connector = OllamaConnector(
        workspace="/tmp",
        allowed_workspaces=["/tmp/allowed"],
        inject_tools_context=False,
    )

    responses = [
        {
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "run_shell_command",
                            "arguments": {"command": "pwd"},
                        }
                    }
                ],
            }
        },
        {"message": {"content": "blocked-handled"}},
    ]

    with (
        patch.object(connector, "_chat", side_effect=lambda **_: responses.pop(0)),
        patch("subprocess.Popen") as mock_popen,
    ):
        result = connector.run_turn(
            "+15551234567",
            "run command",
            options={"allow_tools": True, "cwd": "/etc"},
        )

    assert result == "blocked-handled"
    mock_popen.assert_not_called()


def test_shell_tool_timeout_returns_timeout_payload():
    connector = OllamaConnector(workspace="/tmp", allowed_workspaces=["/tmp"], inject_tools_context=False)

    timeout_proc = _make_mock_proc(
        communicate_side_effect=subprocess.TimeoutExpired("zsh", 1.0)
    )
    with patch("subprocess.Popen", return_value=timeout_proc):
        result = connector._run_shell_tool(sender="+15551234567", command="sleep 5", cwd="/tmp")

    assert "timed_out" in result
    assert "true" in result.lower()
