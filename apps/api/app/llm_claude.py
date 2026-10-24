"""Claude API provider for the AI agents (LLM_PROVIDER=anthropic).

Calls Claude Opus 5.5 through the official Anthropic SDK with a strict JSON
schema (structured outputs), so each agent receives the same dict shape as
from the OpenAI provider in `llm.py`. Credentials are resolved by the SDK:
ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile.

Like the OpenAI path, every failure (no credentials, API error, refusal,
truncated output) raises `LLMUnavailable`; nothing is filled in heuristically.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import anthropic

from .llm import LLMUnavailable

DEFAULT_MODEL = "claude-opus-5-5"
# Opus 5.5 defaults to "medium"; set it explicitly so the choice is visible.
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def has_credentials() -> bool:
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_PROFILE"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))


def complete_json(system: str, user: str, schema: Dict[str, Any], model: str) -> Dict[str, Any]:
    if not has_credentials():
        raise LLMUnavailable("AI が設定されていません（ANTHROPIC_API_KEY 未設定、ant auth login も未実行）")
    client = anthropic.Anthropic(timeout=float(os.getenv("LLM_TIMEOUT", "120")))
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": os.getenv("LLM_EFFORT", DEFAULT_EFFORT),
                "format": {"type": "json_schema", "schema": schema},
            },
            # A safety-classifier decline is re-run server-side on the model
            # Anthropic recommends for that category instead of failing.
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable("AI の認証に失敗しました（Claude API の認証情報を確認してください）") from exc
    except anthropic.RateLimitError as exc:
        raise LLMUnavailable("AI の利用上限に達しました。しばらくしてから再試行してください") from exc
    except anthropic.APIStatusError as exc:
        raise LLMUnavailable(f"AI の呼び出しに失敗しました: HTTP {exc.status_code}") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable("AI に接続できませんでした") from exc

    if response.stop_reason == "refusal":
        raise LLMUnavailable("AI がこの依頼への応答を控えました。手入力で続けてください")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("AI の応答が途中で打ち切られました")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise LLMUnavailable("AI の応答に結果が含まれていませんでした")
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LLMUnavailable("AI の応答を解釈できませんでした") from exc
