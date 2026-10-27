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
        "OPENAI_BASE_URL=http://fixture.invalid/v1\nOPENAI_API_KEY=secret\nLLM_MODEL=fake\n"
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
