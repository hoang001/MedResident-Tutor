"""Small OpenAI-compatible chat client with JSON parsing and bounded retries."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Mapping, Sequence

import httpx
from jsonschema import Draft202012Validator, ValidationError

from .config import Settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM service cannot return a usable response."""

    def __init__(self, message, *, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def parse_json_response(text):
    """Accept plain JSON or one complete Markdown fence; never repair content."""
    text = text.strip().lstrip("\ufeff").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


class LLMClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.llm_base_url:
            raise ValueError("LLM_BASE_URL is required to use the LLM client")

        self._url = settings.endpoint_url(settings.llm_chat_completions_endpoint)
        self._api_key = settings.llm_api_key
        self._timeout = settings.llm_timeout_seconds
        self._max_attempts = settings.llm_max_attempts
        self._prompt_budget_bytes = settings.prompt_budget_bytes
        self._max_output_tokens = settings.max_output_tokens
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self._response_metadata = {}

    def _redact(self, value):
        return value.replace(self._api_key, "[REDACTED]") if self._api_key else value

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def chat_json(
        self,
        model: str,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any] | None = None,
    ) -> Any:
        request_messages = [dict(message) for message in messages]
        if schema is not None:
            request_messages.insert(0,
                {
                    "role": "system",
                    "content": "Return JSON matching this JSON Schema:\n"
                    + json.dumps(schema, ensure_ascii=False),
                }
            )

        base_messages = list(request_messages)
        attempts = []
        for attempt in range(1, self._max_attempts + 1):
            response_text = self._request(model, request_messages)
            try:
                if self._response_metadata.get("finish_reason") == "length":
                    raise ValueError("Response was truncated (finish_reason=length)")
                value = parse_json_response(response_text)
                if schema is not None:
                    Draft202012Validator(schema).validate(value)
                return value
            except (ValueError, ValidationError) as exc:
                if isinstance(exc, ValidationError):
                    kind = "schema_validation"
                    path = "/" + "/".join(str(part) for part in exc.absolute_path)
                    detail = f"Schema rule {exc.validator} failed at {path}: {exc.message}"
                elif isinstance(exc, json.JSONDecodeError):
                    kind = "json_parse"
                    detail = f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
                else:
                    kind = "truncated_response"
                    detail = str(exc)
                detail = self._redact(detail[:1500])
                attempts.append({"attempt": attempt, "error_kind": kind, "detail": detail,
                                 **self._response_metadata,
                                 "raw_response": self._redact(response_text)})
                logger.warning("LLM model=%s attempt=%s error=%s finish_reason=%s", model, attempt, kind, self._response_metadata.get("finish_reason"))
                if attempt == self._max_attempts:
                    raise LLMError(f"LLM failed {kind} after {attempt} attempts", diagnostics={"model": model, "attempts": attempts}) from exc
                correction = {"role": "user", "content": f"Previous output failed: {detail}. Return the complete corrected JSON matching the schema, no Markdown or commentary. Be concise."}
                # Keep only the last failed response; prevent unbounded context growth.
                repair = base_messages + [{"role": "assistant", "content": response_text}, correction]
                if sum(len(m["content"].encode("utf-8")) + 128 for m in repair) > self._prompt_budget_bytes:
                    repair = base_messages + [correction]
                request_messages = repair

        raise LLMError("LLM request ended without a response")

    def _request(self, model: str, messages: list[dict[str, str]]) -> str:
        self._response_metadata = {}
        # Byte-based guard, not a model-independent token counter; configure for your model.
        if sum(len(m["content"].encode("utf-8")) + 128 for m in messages) > self._prompt_budget_bytes:
            raise LLMError("Prompt exceeds configured byte budget; reduce chunk size or adjust LLM_PROMPT_BUDGET_BYTES")
        payload = {"model": model, "messages": messages, "temperature": 0, "max_tokens": self._max_output_tokens}
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.post(
                    self._url,
                    headers=headers,
                    json=payload,
                    timeout=self._timeout,
                )
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise LLMError("LLM request failed after all attempts") from exc
                logger.warning("LLM transport error; retrying attempt %s", attempt + 1)
                time.sleep(min(2 ** (attempt - 1), 4))
                continue

            request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
            logger.info("LLM response status=%s request_id=%s", response.status_code, request_id)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self._max_attempts:
                    raise LLMError(f"LLM service returned HTTP {response.status_code}")
                time.sleep(min(2 ** (attempt - 1), 4))
                continue
            try:
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                self._response_metadata = {
                    "request_id": request_id,
                    "finish_reason": body["choices"][0].get("finish_reason"),
                }
            except (httpx.HTTPStatusError, KeyError, IndexError, TypeError, ValueError) as exc:
                raise LLMError("LLM service returned an invalid response") from exc
            if not isinstance(content, str):
                raise LLMError("LLM response content must be a string")
            return content

        raise LLMError("LLM request ended without a response")
