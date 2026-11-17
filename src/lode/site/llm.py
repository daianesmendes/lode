"""A small client for OpenAI-compatible chat APIs (Gemini, Groq), with a fallback chain.

The models are tried in order: every Gemini model in LLM_MODELS, then every Groq model in
LLM_FALLBACK_MODELS. A model is skipped when it is rate limited, fails, or answers something
that does not fit the expected JSON, so one free tier running out does not stop a batch.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ValidationError

RETRY_STATUS = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str | None = None


@dataclass
class Answer:
    value: BaseModel
    model: str
    seconds: float
    input_tokens: int | None
    output_tokens: int | None


class NoModelAnswered(RuntimeError):
    pass


def endpoints_from_env() -> list[Endpoint]:
    chain = []
    for prefix in ("LLM_", "LLM_FALLBACK_"):
        base, key = os.environ.get(prefix + "BASE_URL"), os.environ.get(prefix + "API_KEY")
        if not base or not key:
            continue
        effort = os.environ.get(prefix + "REASONING_EFFORT") or None
        for model in filter(None, os.environ.get(prefix + "MODELS", "").split(",")):
            chain.append(Endpoint(base.rstrip("/"), key, model.strip(), effort))
    if not chain:
        raise NoModelAnswered("no LLM configured: set LLM_BASE_URL, LLM_API_KEY and LLM_MODELS")
    return chain


def ask(
    client: httpx.Client,
    chain: list[Endpoint],
    messages: list[dict],
    schema: type[BaseModel],
    log: Callable[[str], None] = lambda _: None,
) -> Answer:
    """First valid answer along the chain, parsed into `schema`."""
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
    }
    for endpoint in chain:
        body = {
            "model": endpoint.model,
            "messages": messages,
            "response_format": response_format,
            "temperature": 0,
        }
        if endpoint.reasoning_effort:
            body["reasoning_effort"] = endpoint.reasoning_effort
        started = time.monotonic()
        try:
            response = client.post(
                f"{endpoint.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {endpoint.api_key}"},
            )
        except httpx.HTTPError as exc:
            log(f"{endpoint.model}: {type(exc).__name__}")
            continue
        if response.status_code in RETRY_STATUS or response.status_code >= 400:
            log(f"{endpoint.model}: HTTP {response.status_code}")
            continue
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
            value = schema.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError):
            log(f"{endpoint.model}: answer does not fit {schema.__name__}")
            continue
        usage = data.get("usage") or {}
        return Answer(
            value=value,
            model=endpoint.model,
            seconds=time.monotonic() - started,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )
    raise NoModelAnswered("every model in the chain failed")
