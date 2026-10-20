"""LLM_PROVIDER=anthropic: Claude Opus 5.5 through the Anthropic SDK (no network)."""
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app import llm, llm_claude

SCHEMA = llm.obj({"title": llm.STR})


class FakeClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def _response(text='{"title": "駅周辺の授乳スペース不足"}', stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def install(client):
        monkeypatch.setattr(llm_claude.anthropic, "Anthropic", lambda **kw: client)
        return client

    return install


def test_provider_defaults_to_opus_5_5_with_structured_output_and_fallback(claude):
    client = claude(FakeClient(_response()))
    assert llm.is_configured() and llm.model_name() == "claude-opus-5-5"

    out = llm.complete_json("system prompt", "user prompt", SCHEMA, "draft")

    assert out == {"title": "駅周辺の授乳スペース不足"}
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == "system prompt"
    assert call["messages"] == [{"role": "user", "content": "user prompt"}]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert call["output_config"]["effort"] == "medium"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in call  # Opus 5.5 rejects disabling thinking; effort is the control


def test_refusal_and_truncation_are_failures_not_results(claude):
    claude(FakeClient(_response(text="", stop_reason="refusal")))
    with pytest.raises(llm.LLMUnavailable, match="応答を控えました"):
        llm.complete_json("s", "u", SCHEMA, "draft")
    claude(FakeClient(_response(text='{"title": "途', stop_reason="max_tokens")))
    with pytest.raises(llm.LLMUnavailable, match="打ち切られました"):
        llm.complete_json("s", "u", SCHEMA, "draft")


def test_api_errors_become_llm_unavailable(claude):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    err = anthropic.AuthenticationError(
        "bad key", response=httpx2.Response(401, request=request), body=None)
    claude(FakeClient(error=err))
    with pytest.raises(llm.LLMUnavailable, match="認証"):
        llm.complete_json("s", "u", SCHEMA, "draft")


def test_missing_credentials_is_reported_before_calling(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert not llm.is_configured()
    with pytest.raises(llm.LLMUnavailable, match="ANTHROPIC_API_KEY"):
        llm.complete_json("s", "u", SCHEMA, "draft")


def test_agents_run_unchanged_on_the_claude_provider(claude):
    """An agent built for the OpenAI provider gets the same dict from Claude."""
    from app.agents import chat

    reply = {"reply": "どこで困りましたか？", "organization": [
        {"kind": "experience", "text": "授乳場所が見つからなかった", "source_message_index": 1}]}
    client = claude(FakeClient(_response(json.dumps(reply, ensure_ascii=False))))
    assert chat.respond(None, [{"speaker": "user", "text": "授乳場所がなくて困った"}]) == reply
    assert "organization" in client.calls[0]["output_config"]["format"]["schema"]["properties"]
