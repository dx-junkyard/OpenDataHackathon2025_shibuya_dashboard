"""Reasoning-model client used by every AI agent.

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


def model_name() -> str:
    return os.getenv("LLM_MODEL", "gpt-5.4-mini")


def is_configured() -> bool:
    return os.getenv("LLM_PROVIDER", "openai") == "openai" and bool(os.getenv("LLM_API_KEY"))


def complete_json(system: str, user: str, schema: Dict[str, Any], schema_name: str) -> Dict[str, Any]:
    """Ask the model for a JSON object that satisfies `schema` (strict)."""
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
