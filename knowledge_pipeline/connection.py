"""Connectivity check only; no OCR, extraction, DB access or automatic retries."""

import argparse
from pathlib import Path
import socket
import time
from urllib.parse import urlsplit

from dotenv import dotenv_values
import httpx

from document_toolkit.config import Settings
from document_toolkit.llm_client import parse_json_response


def read_connection_settings(env_file):
    """Read this file explicitly, without loading backend env or mutating os.environ."""
    path = Path(env_file)
    if not path.is_file():
        raise ValueError("ENV_FILE_NOT_FOUND")
    values = dotenv_values(path)
    base = values.get("LLM_BASE_URL") or values.get("OPENAI_BASE_URL") or ""
    key = values.get("LLM_API_KEY") or values.get("OPENAI_API_KEY") or ""
    return Settings(
        llm_base_url=base.strip(),
        llm_api_key=key,
        model=values.get("LLM_MODEL") or "",
        llm_chat_completions_endpoint=values.get("LLM_CHAT_ENDPOINT")
        or "/v1/chat/completions",
        llm_max_attempts=1,
    )


def check_llm(settings, *, tcp_only=False, timeout_seconds=15, client=None):
    """Return a safe result. TCP success does not imply auth/model readiness.

    Default: one tiny generation, potentially billable. No source data is sent.
    The optional HTTP client is for deterministic unit tests.
    """
    started = time.monotonic()
    result = {
        "ok": False,
        "mode": "tcp" if tcp_only else "model",
        "code": "CONFIG_ERROR",
    }

    def finish(code, ok=False, **fields):
        return {
            **result,
            **fields,
            "ok": ok,
            "code": code,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    if not 0 < timeout_seconds <= 300:
        return finish("INVALID_TIMEOUT")
    try:
        url = settings.endpoint_url(settings.llm_chat_completions_endpoint)
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return finish("INVALID_URL")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return finish("INVALID_URL")
    if tcp_only:
        try:
            with socket.create_connection(
                (parsed.hostname, port), timeout=timeout_seconds
            ):
                return finish("TCP_CONNECTED", True)
        except socket.gaierror:
            return finish("DNS_ERROR")
        except TimeoutError:
            return finish("CONNECT_TIMEOUT")
        except OSError:
            return finish("TCP_CONNECTION_FAILED")
    if (
        not settings.llm_api_key
        or settings.llm_api_key.startswith("<")
        or not settings.model
    ):
        return finish("MISSING_KEY_OR_MODEL")

    def request(http):
        return http.post(
            url,
            headers={"Authorization": "Bearer " + settings.llm_api_key},
            json={
                "model": settings.model,
                "messages": [
                    {"role": "user", "content": 'Return only JSON: {"ok":true}'}
                ],
                "temperature": 0,
                "max_tokens": 64,
            },
            timeout=timeout_seconds,
        )

    try:
        if client is not None:
            response = request(client)
        else:
            with httpx.Client(trust_env=False, follow_redirects=False) as http:
                response = request(http)
    except httpx.ConnectTimeout:
        return finish("CONNECT_TIMEOUT")
    except httpx.TimeoutException:
        return finish("RESPONSE_TIMEOUT")
    except httpx.RequestError:
        return finish("CONNECTION_ERROR")
    status = response.status_code
    if status != 200:
        # Never print raw bodies/exception strings: they may contain private URLs or keys.
        error_type = None
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            kind = error.get("type") if isinstance(error, dict) else None
            if kind in (
                "no_db_connection",
                "authentication_error",
                "invalid_api_key",
                "model_not_found",
            ):
                error_type = kind
        except ValueError:
            pass
        return finish(
            "API_NO_DB_CONNECTION"
            if error_type == "no_db_connection"
            else "HTTP_ERROR",
            http_status=status,
            error_type=error_type,
        )
    try:
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") == "length":
            return finish("OUTPUT_TRUNCATED", http_status=status)
        if parse_json_response(choice["message"]["content"]) != {"ok": True}:
            return finish("UNEXPECTED_OUTPUT", http_status=status)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return finish("INVALID_JSON_OUTPUT", http_status=status)
    return finish("MODEL_OK", True, http_status=status)


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, default=Path("knowledge_pipeline/.env")
    )
    parser.add_argument(
        "--tcp-only",
        action="store_true",
        help="Only open TCP socket; no model call/cost",
    )
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    try:
        result = check_llm(
            read_connection_settings(args.env_file),
            tcp_only=args.tcp_only,
            timeout_seconds=args.timeout,
        )
    except ValueError:
        result = {
            "ok": False,
            "code": "CONFIG_ERROR",
            "hint": "Check env-file and LLM configuration",
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
