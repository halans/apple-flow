from apple_flow.egress import IMessageEgress


def test_suppresses_duplicate_outbound_within_window(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    egress.send("+15551234567", "Hello world")
    egress.send("+15551234567", "Hello world")

    assert len(sent_calls) == 1


def test_chunked_send_marks_full_text_for_echo_detection(monkeypatch):
    sent_calls = []

    def fake_send(_recipient: str, _text: str) -> None:
        sent_calls.append((_recipient, _text))

    egress = IMessageEgress(max_chunk_chars=10, suppress_duplicate_outbound_seconds=120)
    monkeypatch.setattr(egress, "_osascript_send", fake_send)

    text = "0123456789ABCDEFGHIJ"  # 2 chunks
    egress.send("+15551234567", text)

    assert len(sent_calls) == 2
    assert egress.was_recent_outbound("+15551234567", text)
    assert egress.was_recent_outbound("+15551234567", "0123456789")

    # Duplicate full payload should be suppressed even when original send chunked.
    egress.send("+15551234567", text)
    assert len(sent_calls) == 2
