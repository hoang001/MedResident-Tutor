"""Single-attempt OpenAI-compatible transport for user-configured inference servers."""

import json
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.modules.practice.contracts import ServiceError, strict_json


def configured(value):
    return bool(value and value.strip() and "<" not in value and ">" not in value)


def chat_url(base):
    if not configured(base):
        raise ServiceError("REMOTE_MODEL_NOT_CONFIGURED", 503)
    parsed = urlsplit(base.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ServiceError("REMOTE_MODEL_URL_INVALID", 503)
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions" if path.endswith("/v1") else "/v1/chat/completions"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


async def chat(*, base, key, model, messages, max_tokens, timeout, request_id=None):
    if not configured(key) or not configured(model):
        raise ServiceError("REMOTE_MODEL_NOT_CONFIGURED", 503)
    url = chat_url(base)
    headers = {"Authorization": "Bearer " + key}
    if request_id:
        headers["X-Request-ID"] = request_id
    try:
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0,
                    "stream": False,
                },
            )
        if response.status_code == 429:
            raise ServiceError("PROVIDER_BUSY", 429)
        if not response.is_success:
            # Preserve HTTP status, never expose an upstream message that may echo secrets.
            raise ServiceError("REMOTE_HTTP_" + str(response.status_code), response.status_code)
        data = strict_json(response.text)
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ServiceError("MODEL_OUTPUT_TRUNCATED", 502)
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Expected text completion")
        value = strict_json(content)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value, {
            "requested_model": model,
            "reported_model": data.get("model"),
            "usage": data.get("usage", {}),
            "api_format": "openai",
            "finish_reason": choice.get("finish_reason"),
        }
    except httpx.TimeoutException:
        raise ServiceError("PROVIDER_TIMEOUT", 504) from None
    except httpx.HTTPError:
        raise ServiceError("PROVIDER_CONNECTION_FAILED", 502) from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise ServiceError("PROVIDER_RESPONSE_INVALID", 502) from None


def grading_messages(stage, payload):
    if stage == "medical":
        from src.medical.inference import SYSTEM_PROMPT, build_user_content

        content = build_user_content(payload)
    elif stage == "teaching":
        from src.teaching.prepare_dataset import SYSTEM_PROMPT

        content = json.dumps(
            {
                key: payload[key]
                for key in (
                    "question",
                    "student_answer",
                    "medical_evaluation",
                    "learner_context",
                    "metadata",
                )
            },
            ensure_ascii=False,
        )
    else:
        raise ServiceError("HTTP_STAGE_NOT_CONFIGURED", 503)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]
