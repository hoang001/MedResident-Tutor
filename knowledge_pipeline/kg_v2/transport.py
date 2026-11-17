"""One shared sequential budget, typed safe diagnostics, no hidden HTTP retries."""

import json
import time

import httpx

from document_toolkit.llm_client import LLMClient, LLMError


class BudgetExhausted(RuntimeError):
    pass


class RequestBudget:
    def __init__(self, max_calls, total_seconds):
        if max_calls < 1 or (total_seconds is not None and total_seconds <= 0):
            raise ValueError("positive_request_and_time_budget_required")
        self.max_calls, self.total_seconds = max_calls, total_seconds
        self.calls, self.wait_seconds = 0, 0.0
        self.blocked = False

    def begin(self, timeout):
        remaining = (
            self.total_seconds - self.wait_seconds
            if self.total_seconds is not None
            else None
        )
        if (
            self.blocked
            or self.calls >= self.max_calls
            or (remaining is not None and remaining <= 0)
        ):
            raise BudgetExhausted("request_or_wait_budget_exhausted")
        self.calls += 1
        if remaining is None:
            return timeout
        return min(timeout, remaining) if timeout is not None else remaining

    def snapshot(self):
        return {
            "attempts": self.calls,
            "max_calls": self.max_calls,
            "wait_seconds": round(self.wait_seconds, 3),
            "total_seconds": self.total_seconds,
            "blocked_configuration_or_auth": self.blocked,
        }


class BudgetedLLM(LLMClient):
    def __init__(
        self,
        settings,
        client,
        budget,
        save_metrics,
        *,
        no_response_timeout=False,
        connect_timeout_seconds=30,
    ):
        super().__init__(settings, client)
        if connect_timeout_seconds <= 0:
            raise ValueError("positive_connection_timeout_required")
        if no_response_timeout and budget.total_seconds is not None:
            raise ValueError("unlimited_response_requires_unlimited_wait_budget")
        self.no_response_timeout = no_response_timeout
        self.connect_timeout_seconds = connect_timeout_seconds
        self.budget, self.save_metrics = budget, save_metrics
        self.metrics = []
        self.window_id = None

    def _request(self, model, messages):
        if (
            sum(len(m["content"].encode("utf-8")) + 128 for m in messages)
            > self._prompt_budget_bytes
        ):
            self.budget.blocked = True
            raise LLMError(
                "prompt_byte_budget_exceeded",
                diagnostics={"category": "configuration", "retryable": False},
            )
        timeout = self.budget.begin(None if self.no_response_timeout else self._timeout)
        http_timeout = (
            httpx.Timeout(None, connect=self.connect_timeout_seconds)
            if self.no_response_timeout
            else timeout
        )
        started = time.monotonic()
        row = {
            "window_id": self.window_id,
            "attempt": self.budget.calls,
            "timeout_seconds": round(timeout, 3) if timeout is not None else None,
            "http_status": None,
            "category": "unknown",
            "retryable": False,
        }
        if self.no_response_timeout:
            row["connect_timeout_seconds"] = self.connect_timeout_seconds
        try:
            response = self._client.post(
                self._url,
                headers={"Authorization": "Bearer " + self._api_key},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": self._max_output_tokens,
                },
                timeout=http_timeout,
            )
            row["http_status"] = response.status_code
            if response.status_code != 200:
                row["category"] = (
                    "rate_limit"
                    if response.status_code == 429
                    else "authentication"
                    if response.status_code in (401, 403)
                    else "server"
                    if response.status_code >= 500
                    else "http_error"
                )
                row["retryable"] = (
                    response.status_code == 429 or response.status_code >= 500
                )
                if response.status_code in (400, 401, 403, 404):
                    self.budget.blocked = True
                try:
                    err = response.json().get("error", {})
                    if isinstance(err, dict):
                        row["error_type"] = self._redact(str(err.get("type", "")))[:200]
                        row["message"] = self._redact(str(err.get("message", "")))[
                            :1000
                        ]
                except (ValueError, AttributeError):
                    pass
                raise LLMError("http_request_failed", diagnostics=row)
            try:
                body = response.json()
                choice = body["choices"][0]
                content = choice["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("response_content_not_string")
                usage = body.get("usage", {})
                row["usage"] = (
                    {k: v for k, v in usage.items() if isinstance(v, (int, float))}
                    if isinstance(usage, dict)
                    else {}
                )
                row["finish_reason"] = choice.get("finish_reason")
                self._response_metadata = {"finish_reason": choice.get("finish_reason")}
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                row.update(category="parse", error_type=type(exc).__name__)
                raise LLMError("invalid_response_envelope", diagnostics=row) from exc
            row["category"] = "response_received"
            return content
        except httpx.TimeoutException as exc:
            row.update(
                category="timeout", error_type=type(exc).__name__, retryable=True
            )
            raise LLMError("request_timeout", diagnostics=row) from exc
        except httpx.RequestError as exc:
            row.update(
                category="connection", error_type=type(exc).__name__, retryable=True
            )
            raise LLMError("connection_failed", diagnostics=row) from exc
        finally:
            elapsed = time.monotonic() - started
            self.budget.wait_seconds += elapsed
            row["latency_seconds"] = round(elapsed, 3)
            self.metrics.append(row)
            self.save_metrics(self.metrics)

    def chat_json(self, *args, **kwargs):
        try:
            return super().chat_json(*args, **kwargs)
        except LLMError as exc:
            if exc.diagnostics.get("attempts"):
                kinds = {r["error_kind"] for r in exc.diagnostics["attempts"]}
                category = (
                    "schema"
                    if "schema_validation" in kinds
                    else "truncated"
                    if "truncated_response" in kinds
                    else "parse"
                )
                exc.diagnostics.update(category=category, retryable=False)
                if self.metrics:
                    self.metrics[-1].update(category=category, retryable=False)
                    self.save_metrics(self.metrics)
            # Only redacted, structured diagnostics reach audit. Never serialize settings.
            exc.diagnostics = json.loads(self._redact(json.dumps(exc.diagnostics)))
            raise
