"""Benchmark Medical API models on the locked validation split (no GPU required).

Uses the baseline module directly; its torch/transformers imports must be installed.
Configuration is read from process environment variables, not automatically from .env.
"""

import argparse
import json
import math
import os
import socket
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL_ENV = {
    "gemma-4-12b-it": "MEDICAL_BENCHMARK_MODEL_12B",
    "gemma-4-26b": "MEDICAL_BENCHMARK_MODEL_26B",
}


class NoRedirect(HTTPRedirectHandler):
    """Do not forward the Authorization header to a redirected destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_api(url, api_key, model_name, messages, max_tokens, timeout):
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    opener = build_opener(NoRedirect())
    start = time.perf_counter()
    result = {"raw_response": "", "api_error": None, "attempts": 0}
    for attempt in range(3):  # One initial request and at most two retries.
        result["attempts"] = attempt + 1
        retryable = False
        try:
            with opener.open(request, timeout=timeout) as response:
                body = response.read()
            try:
                envelope = json.loads(body)
            except (ValueError, UnicodeError):
                result["api_error"] = "API response is not valid JSON."
                break
            try:
                content = envelope["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError
            except (KeyError, IndexError, TypeError, ValueError):
                result["api_error"] = "Missing or invalid choices[0].message.content."
                break
            result["raw_response"] = content
            result["api_error"] = None
            break
        except HTTPError as exc:
            # Do not log response bodies, URLs, headers or exception text: may contain secrets.
            result["api_error"] = f"HTTP {exc.code}"
            retryable = 500 <= exc.code < 600
            exc.close()
        except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError, HTTPException):
            result["api_error"] = "Network error or request timeout."
            retryable = True
        if not retryable or attempt == 2:
            break
        time.sleep(2 ** attempt)
    # End-to-end wall time, including any retries/backoff; recorded explicitly in report.
    result["latency_seconds"] = round(time.perf_counter() - start, 4)
    return result


def score_response(row, response, baseline):
    result = {
        "sample_id": row["sample_id"], "question_id": row["question_id"],
        **response,
        "gold": json.loads(row["messages"][-1]["content"]),
        "prediction": None, "json_valid": False, "parse_error": None,
        "contract_valid": False, "contract_errors": [], "comparison": None,
    }
    if response["api_error"]:
        result["contract_errors"] = ["No assistant response from API."]
        return result
    prediction, parse_error = baseline.extract_json(response["raw_response"])
    result.update(prediction=prediction, parse_error=parse_error, json_valid=prediction is not None)
    if prediction is None:
        result["contract_errors"] = ["Không parse được JSON."]
        return result
    errors = baseline.validate_contract(prediction)
    result.update(contract_errors=errors, contract_valid=not errors)
    try:
        # Preserve baseline scoring even for contract-invalid objects where comparison is possible.
        result["comparison"] = baseline.compare_with_gold(prediction, result["gold"])
    except (AttributeError, TypeError, ValueError):
        # Malformed model output must not abort the remaining validation samples or trigger retry.
        result["comparison_error"] = "Malformed prediction cannot be compared with gold."
    return result


def evaluate_model(alias, model_name, rows, baseline, comparison_metrics, url, api_key, timeout):
    results = []
    for index, row in enumerate(rows, start=1):
        print(f"\n[{index}/{len(rows)}] {row['sample_id']}")
        response = call_api(
            url, api_key, model_name, row["messages"][:-1], baseline.MAX_NEW_TOKENS, timeout,
        )
        result = score_response(row, response, baseline)
        results.append(result)
        print("JSON:", "PASS" if result["json_valid"] else "FAIL")
        print("Contract:", "PASS" if result["contract_valid"] else "FAIL")
        for _, key, label in comparison_metrics:
            passed = bool(result["comparison"]) and result["comparison"][key]
            print(f"{label}:", "PASS" if passed else "FAIL")
        if result["api_error"]:
            print("API error:", result["api_error"])

    total = len(results)
    metrics = {
        key: {"passed": sum(item[key] for item in results), "total": total}
        for key in ("json_valid", "contract_valid")
    }
    for report_key, comparison_key, _ in comparison_metrics:
        metrics[report_key] = {
            "passed": sum(
                bool(item["comparison"]) and item["comparison"][comparison_key]
                for item in results
            ),
            "total": total,
        }
    average_latency = sum(item["latency_seconds"] for item in results) / total
    metrics["average_latency_seconds"] = round(average_latency, 4)
    report = {
        "model_id": model_name,
        "dataset": str(baseline.VALIDATION_FILE.relative_to(baseline.ROOT)),
        "total_samples": total,
        "generation_config": {"temperature": 0, "max_tokens": baseline.MAX_NEW_TOKENS},
        "latency_policy": "End-to-end API wall time including retries/backoff, all samples.",
        "api_error_count": sum(item["api_error"] is not None for item in results),
        "metrics": metrics, "cases": results,
    }
    output_dir = baseline.ROOT / "model-training" / "outputs" / "medical-api-benchmark"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{alias}-validation.json"
    # Redact even if a server unexpectedly echoes the credential in generated text.
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    escaped_key = json.dumps(api_key, ensure_ascii=False)[1:-1]
    output_file.write_text(serialized.replace(escaped_key, "[REDACTED]"), encoding="utf-8")

    print(f"\n=== API MODEL SUMMARY: {model_name.replace(api_key, '[REDACTED]')} ===")
    for key, label in (
        ("json_valid", "JSON valid"), ("contract_valid", "Contract valid"),
        *((key, label) for key, _, label in comparison_metrics),
    ):
        print(f"{label}:", f"{metrics[key]['passed']}/{total}")
    print("Average latency:", f"{average_latency:.2f}s")
    print("Saved:", output_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--model", choices=MODEL_ENV)
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=float, default=120, help="Request timeout in seconds")
    cli = parser.parse_args()
    if not math.isfinite(cli.timeout) or cli.timeout <= 0:
        parser.error("--timeout must be finite and positive")
    base_url = os.environ.get("MEDICAL_BENCHMARK_LLM_BASE_URL", "").strip()
    api_key = os.environ.get("MEDICAL_BENCHMARK_LLM_API_KEY", "").strip()
    endpoint = os.environ.get("MEDICAL_BENCHMARK_CHAT_ENDPOINT", "/v1/chat/completions").strip()
    if not base_url or not api_key:
        parser.error("Set MEDICAL_BENCHMARK_LLM_BASE_URL and MEDICAL_BENCHMARK_LLM_API_KEY")
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username \
            or parsed.password or parsed.query or parsed.fragment:
        parser.error("BASE_URL must be an HTTP(S) URL without credentials, query or fragment")
    if not endpoint.startswith("/") or endpoint.startswith("//") or "?" in endpoint or "#" in endpoint:
        parser.error("CHAT_ENDPOINT must be an absolute URL path without query or fragment")
    url = base_url.rstrip("/") + endpoint

    if __package__:
        from . import evaluate_baseline as baseline
        from .evaluate_adapter import COMPARISON_METRICS
    else:
        import evaluate_baseline as baseline
        from evaluate_adapter import COMPARISON_METRICS

    rows = baseline.read_jsonl(baseline.VALIDATION_FILE)
    if len(rows) != 8 or len({row["sample_id"] for row in rows}) != 8:
        raise ValueError("Validation must contain exactly 8 unique samples.")
    for row in rows:
        messages = row["messages"]
        if [m["role"] for m in messages] != ["system", "user", "assistant"]:
            raise ValueError("Expected exactly system/user/assistant messages in validation.")
        if any(not isinstance(m["content"], str) for m in messages):
            raise ValueError("Validation message content must be a string.")
        json.loads(messages[-1]["content"])
    for alias in MODEL_ENV if cli.all else [cli.model]:
        model_name = os.environ.get(MODEL_ENV[alias], alias).strip()
        if not model_name:
            parser.error(f"{MODEL_ENV[alias]} must not be empty")
        evaluate_model(
            alias, model_name, rows, baseline, COMPARISON_METRICS, url, api_key, cli.timeout,
        )


if __name__ == "__main__":
    main()
