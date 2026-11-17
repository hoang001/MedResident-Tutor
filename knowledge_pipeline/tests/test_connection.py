import json

import httpx
import pytest

from document_toolkit.config import Settings
from knowledge_pipeline.connection import check_llm, read_connection_settings


@pytest.mark.parametrize(
    "scenario,code",
    [
        ("success", "MODEL_OK"),
        ("db", "API_NO_DB_CONNECTION"),
        ("nginx", "HTTP_ERROR"),
        ("timeout", "CONNECT_TIMEOUT"),
        ("invalid", "INVALID_JSON_OUTPUT"),
        ("truncated", "OUTPUT_TRUNCATED"),
    ],
)
def test_http_probe(scenario, code):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.path == "/v1/chat/completions"
        if scenario == "timeout":
            raise httpx.ConnectTimeout("private-url-and-secret", request=request)
        if scenario == "db":
            return httpx.Response(
                400,
                json={
                    "error": {"type": "no_db_connection", "message": "private-secret"}
                },
            )
        if scenario == "nginx":
            return httpx.Response(503, text="private-secret")
        if scenario == "invalid":
            return httpx.Response(200, json={"choices": []})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"ok":true}'},
                        "finish_reason": "length"
                        if scenario == "truncated"
                        else "stop",
                    }
                ]
            },
        )

    settings = Settings(
        llm_base_url="http://fixture.invalid/v1",
        llm_api_key="private-secret",
        model="fake",
    )
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = check_llm(settings, client=client)
    assert len(requests) == 1
    assert result["code"] == code and result["ok"] == (scenario == "success")
    assert "private-secret" not in json.dumps(result)
    assert "fixture.invalid" not in json.dumps(result)


def test_explicit_env_file_and_no_double_v1(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "LLM_BASE_URL=http://fixture.invalid/v1\nLLM_API_KEY=secret\nLLM_MODEL=fake\n"
    )
    settings = read_connection_settings(path)
    assert (
        settings.endpoint_url(settings.llm_chat_completions_endpoint)
        == "http://fixture.invalid/v1/chat/completions"
    )


def test_tcp_does_not_call_model(monkeypatch):
    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(
        "knowledge_pipeline.connection.socket.create_connection",
        lambda *a, **k: Socket(),
    )
    result = check_llm(
        Settings(llm_base_url="http://fixture.invalid/v1"), tcp_only=True
    )
    assert result["ok"] and result["code"] == "TCP_CONNECTED"


def test_explicit_file_ignores_terminal_and_legacy_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://old.invalid")
    monkeypatch.setenv("LLM_API_KEY", "old-terminal-key")
    monkeypatch.setenv("OPENAI_API_KEY", "old-openai-key")
    monkeypatch.setenv("KG_LLM_API_KEY", "old-kg-key")
    path = tmp_path / ".env"
    path.write_text("LLM_BASE_URL=http://10.8.0.1:4000/v1\n"
                    "LLM_API_KEY=<TOI_SE_TU_DIEN>\nLLM_MODEL=vtllm/gemma-4-26b\n"
                    "LLM_CHAT_ENDPOINT=/v1/chat/completions\nOPENAI_API_KEY=old-file-key\n")
    settings = read_connection_settings(path)
    assert settings.endpoint_url(settings.llm_chat_completions_endpoint) == (
        "http://10.8.0.1:4000/v1/chat/completions"
    )
    assert settings.llm_api_key == "<TOI_SE_TU_DIEN>"
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("No API call"))) as client:
        assert check_llm(settings, client=client, reply_ok=True)["code"] == "MISSING_KEY_OR_MODEL"
    path.write_text("LLM_MODEL=test\nOPENAI_API_KEY=old-file-key\n")
    assert read_connection_settings(path).llm_api_key == ""
    # Extraction uses the same file-only priority and never reuses terminal keys.
    assert Settings.from_env(path).llm_api_key == ""
    assert Settings.from_env(path).model == "test"


@pytest.mark.parametrize("status", [200, 503])
def test_ok_probe_one_request_and_redacted_diagnostics(status):
    calls = []

    def handle(request):
        calls.append(request)
        assert json.loads(request.content)["messages"][0]["content"] == "Reply with exactly OK."
        if status == 200:
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(status, json={"error": {
            "type": "upstream_failure", "message": "Service error with test-private-key",
        }})

    settings = Settings(llm_base_url="http://fixture.invalid/v1",
                        llm_api_key="test-private-key", model="fake")
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = check_llm(settings, client=client, reply_ok=True)
    assert len(calls) == 1
    assert result["http_status"] == status
    assert "test-private-key" not in json.dumps(result)
    if status == 200:
        assert result["response_content"] == "OK"
    else:
        assert result["error_type"] == "upstream_failure"
        assert result["error_message"] == "Service error with [REDACTED]"
