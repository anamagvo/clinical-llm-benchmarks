"""HTTP streams are fixed fixtures, not model runs."""
import json
from model_adapters.streaming import consume_stream


class Stream:
    def __init__(self, chunks, interrupt=False):
        self.chunks, self.interrupt = chunks, interrupt

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self.chunks
        if self.interrupt:
            raise KeyboardInterrupt


def test_openai_usage_only_chunk(monkeypatch):
    chunks = [b'data: {"choices":[{"delta":{"content":"Gr\\u00fc\\u00dfe"}}]}',
              b'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":4}}', b'data: [DONE]']
    monkeypatch.setattr("model_adapters.streaming.requests.post", lambda *a, **kw: Stream(chunks))
    response = consume_stream("fixture", {}, {}, "openai", [10, 300])
    assert response.text == "Grüße"
    assert response.input_tokens == 11
    assert response.output_tokens == 4
    assert response.ttft_s is not None
    assert response.error is None


def test_interruption_preserves_partial_response(monkeypatch):
    chunks = [json.dumps({"message": {"content": "Teilantwort"}}).encode()]
    monkeypatch.setattr("model_adapters.streaming.requests.post", lambda *a, **kw: Stream(chunks, True))
    response = consume_stream("fixture", {}, {}, "ollama", [10, 300])
    assert response.text == "Teilantwort"
    assert response.interrupted is True
    assert response.output_tokens is None


def test_truncated_stream_is_failure(monkeypatch):
    monkeypatch.setattr("model_adapters.streaming.requests.post", lambda *a, **kw: Stream([]))
    response = consume_stream("fixture", {}, {}, "ollama", [10, 300])
    assert response.error == "Stream ended without completion marker"
    assert response.token_source == "unavailable"