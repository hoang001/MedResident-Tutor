import io
import json
import sys

from app.scripts import integration_case


def test_payload_stdout_is_utf8_on_legacy_windows_pipe(monkeypatch, tmp_path):
    result = {"question": "Câu hỏi tiếng Việt", "student_answer": "Câu trả lời thử"}

    async def fake_run(args):
        return result

    buffer = io.BytesIO()
    pipe = io.TextIOWrapper(buffer, encoding="ascii")
    monkeypatch.setattr(integration_case, "run", fake_run)
    monkeypatch.setattr(sys, "stdout", pipe)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "integration_case",
            "--repo-root",
            str(tmp_path),
            "payload",
            "--question-id",
            "TEST_Q",
            "--student-answer",
            "Câu trả lời thử",
        ],
    )
    integration_case.main()
    pipe.flush()
    assert json.loads(buffer.getvalue().decode("utf-8")) == result
