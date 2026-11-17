"""Real local BE checks without a model invocation or new practice attempt."""

import uuid
import httpx

from .common import ROOT, REPORT, read, write


def main():
    users = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"]
    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=30) as client:
        response = client.post(
            "/auth/login", json={k: users[0][k] for k in ("email", "password")}
        )
        assert response.status_code == 200, (
            "Existing review account login failed; no account created"
        )
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        config = client.get("/practice/config")
        assert config.status_code == 200
        before = client.get("/practice/attempts")
        assert before.status_code == 200
        checks = []
        for suffix in ("CASE01", "XR01"):
            qid = "CLINICAL_DEMO_V1_" + suffix
            learner = client.get("/practice/questions/" + qid)
            assert learner.status_code == 200

            def no_gold(obj):
                if isinstance(obj, dict):
                    assert not (
                        set(obj)
                        & {
                            "rubric",
                            "criteria",
                            "reference_answer",
                            "evidence",
                            "answer_annotations",
                            "source_image_id",
                        }
                    )
                    for value in obj.values():
                        no_gold(value)
                elif isinstance(obj, list):
                    for value in obj:
                        no_gold(value)

            no_gold(learner.json())
            response = client.post(
                "/practice/attempts",
                headers={"Idempotency-Key": uuid.uuid4().hex},
                json={"question_id": qid, "student_answer": ""},
            )
            assert response.status_code == 422
            checks.append(
                {
                    "question_id": qid,
                    "learner_payload_no_gold": True,
                    "empty_answer_http": 422,
                }
            )
        after = client.get("/practice/attempts")
        assert after.json() == before.json(), (
            "Blank request unexpectedly changed attempt history"
        )
        write(
            REPORT / "app-preflight.json",
            {
                "scope": "real BE; existing development provider; no model inference",
                "provider": config.json(),
                "checks": checks,
                "attempt_history_unchanged": True,
                "real_medical_http_practice": "not_run",
                "mastery_updated": False,
            },
        )
        print(
            "Real backend: 2 empty answers rejected HTTP 422; no attempt created; learner payload checked. No model call."
        )


if __name__ == "__main__":
    main()
