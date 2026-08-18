"""The urllib chat client: same protocol as the OpenAI SDK, no dependencies, runs in Pyodide."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from aquascope.ai_engine import analyst
from aquascope.ai_engine.llm_transport import LLMHTTPError, UrllibChatClient, make_client


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_client_posts_openai_shape_and_wraps_response():
    seen = {}

    def urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return _Resp({"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "find_stations", "arguments": '{"query": "seine"}'}}
        ]}}]})

    client = UrllibChatClient("sk-test", "https://api.groq.com/openai/v1/")
    with patch("urllib.request.urlopen", urlopen):
        resp = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "hi"}],
                                              tools=[{"type": "function"}], tool_choice="auto")
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["body"]["model"] == "m" and seen["body"]["tool_choice"] == "auto"
    msg = resp.choices[0].message
    assert msg.content is None and msg.tool_calls[0].function.name == "find_stations"
    assert msg.tool_calls[0].id == "c1" and json.loads(msg.tool_calls[0].function.arguments) == {"query": "seine"}
    assert msg.missing_field is None  # optional SDK fields read as None


def test_http_errors_are_explained():
    def urlopen(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", None, io.BytesIO(b'{"error":"bad key"}'))

    client = UrllibChatClient("bad", "https://api.openai.com/v1")
    with patch("urllib.request.urlopen", urlopen), pytest.raises(LLMHTTPError) as ei:
        client.chat.completions.create(model="m", messages=[])
    assert ei.value.status == 401 and "rejected" in str(ei.value) and "bad key" in str(ei.value)


def test_ask_runs_the_full_loop_over_urllib(monkeypatch):
    """ask() with the urllib transport: two model turns (one tool call, then the answer)."""
    monkeypatch.setenv("AQUASCOPE_LLM_TRANSPORT", "urllib")
    turns = iter([
        {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "t1", "type": "function", "function": {"name": "describe_methods", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"content": "GEV and LP3 are used, see methods."}}]},
    ])
    posted = []

    def urlopen(req, timeout=0):
        posted.append(json.loads(req.data))
        return _Resp(next(turns))

    with patch("urllib.request.urlopen", urlopen):
        res = analyst.ask("what methods?", provider="groq", api_key="k", model="llama")
    assert res.answer.startswith("GEV") and res.provider == "groq" and res.model == "llama"
    assert [c.name for c in res.tool_calls] == ["describe_methods"] and res.tool_calls[0].ok
    assert posted[1]["messages"][-1]["role"] == "tool" and posted[1]["messages"][-1]["tool_call_id"] == "t1"
    md = res.to_markdown()
    assert md.startswith("# what methods?") and "Tools called: describe_methods" in md


def test_make_client_falls_back_to_urllib_when_forced(monkeypatch):
    monkeypatch.setenv("AQUASCOPE_LLM_TRANSPORT", "urllib")
    assert isinstance(make_client("k", None), UrllibChatClient)
    monkeypatch.setenv("AQUASCOPE_LLM_TRANSPORT", "")
    with patch.dict("sys.modules", {"openai": None}):  # openai not installed
        assert isinstance(make_client("k", "http://x/v1"), UrllibChatClient)


def test_catalog_override_feeds_find_stations():
    from aquascope import mcp_server
    from aquascope.archive import catalog

    rows = [{"source": "usgs", "station_id": "USGS-1", "name": "Potomac River", "latitude": 38.9, "longitude": -77.1,
             "variables": ["discharge"]}]
    catalog.set_catalog(rows)
    try:
        out = mcp_server.find_stations(query="potomac")
        assert out["n_catalog"] == 1 and out["stations"][0]["station_id"] == "USGS-1"
    finally:
        catalog.set_catalog(None)
