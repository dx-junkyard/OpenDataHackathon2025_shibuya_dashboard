"""Reasoning-model client used by every AI agent.

LLM_PROVIDER selects the backend: "openai" (default, OpenAI-compatible chat
completions below) or "anthropic" (Claude Opus 5.5 via the Anthropic SDK, in
`llm_claude.py`). LLM_MODEL overrides the provider's default model.

The agents only ever produce proposals (docs/features.md F-21). When no model
is configured, or the call fails, `LLMUnavailable` is raised so the caller can
show the failure and fall back to manual input (F-18). There is deliberately
no heuristic fallback that would make a failed AI call look successful.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import httpx


class LLMUnavailable(RuntimeError):
    """The model could not be used; callers must surface this, not hide it."""


PROVIDERS = ("openai", "anthropic")


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "openai")


def model_name() -> str:
    default = "claude-opus-5-5" if provider() == "anthropic" else "gpt-5.4-mini"
    return os.getenv("LLM_MODEL") or default


def is_configured() -> bool:
    if provider() == "anthropic":
        from .llm_claude import has_credentials

        return has_credentials()
    return provider() == "openai" and bool(os.getenv("LLM_API_KEY"))


def complete_json(system: str, user: str, schema: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
    """Ask the model for a JSON object that satisfies `schema` (strict)."""
    if provider() not in PROVIDERS:
        raise LLMUnavailable(f"未知の LLM_PROVIDER です: {provider()}")
    if provider() == "anthropic":
        from .llm_claude import complete_json as claude_complete_json

        return claude_complete_json(system, user, schema, model_name())
    if not is_configured():
        raise LLMUnavailable("AI が設定されていません（LLM_API_KEY 未設定）")
    base = os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
            json={
                "model": model_name(),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
            },
            timeout=float(os.getenv("LLM_TIMEOUT", "90")),
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise LLMUnavailable(f"AI の呼び出しに失敗しました: {type(exc).__name__}") from exc


def obj(properties: Dict[str, Any]) -> Dict[str, Any]:
    """Strict JSON-schema object helper: every property is required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def enum(values: list[str]) -> Dict[str, Any]:
    return {"type": "string", "enum": values}


STR = {"type": "string"}
