"""Exercise the real local API with private development-only review accounts."""
import hashlib
import json
import secrets
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000/api/v1"
PRIVATE = ROOT / "data/backups/clinical-demo-accounts.json"
DEMO_IDS = ["CLINICAL_DEMO_V1_CASE01", "CLINICAL_DEMO_V1_XR01"]
ANSWER = "Câu trả lời thử luồng dữ liệu, không dùng để đánh giá năng lực."


def main():
    if PRIVATE.exists():
        private = json.loads(PRIVATE.read_text(encoding="utf-8"))
    else:
        run = uuid.uuid4().hex[:12]
        private = {"users": [{"email": f"clinical-demo-{run}-{i}@example.com", "password": secrets.token_urlsafe(24), "full_name": "Clinical demo review"} for i in range(2)], "keys": {qid: uuid.uuid4().hex for qid in DEMO_IDS}}
        PRIVATE.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE.write_text(json.dumps(private), encoding="utf-8")
    tokens = []
    client = httpx.Client(timeout=40)
    for user in private["users"]:
        login = client.post(BASE + "/auth/login", json={k: user[k] for k in ("email", "password")})
        if login.status_code == 401:
            registered = client.post(BASE + "/auth/register", json=user)
            assert registered.status_code == 201
            login = client.post(BASE + "/auth/login", json={k: user[k] for k in ("email", "password")})
        assert login.status_code == 200
        tokens.append(login.json()["access_token"])
    h1, h2 = [{"Authorization": "Bearer " + token} for token in tokens]
    assert client.get(BASE + "/practice/config", headers=h1).json()["execution_mode"] == "mock"
    checks, attempts = [], []
    banned = {"rubric", "criteria", "reference_answer", "reference_answer_vi", "answer_annotations", "annotations", "source_refs", "source_image_id", "annotation_path", "storage_key", "attribution_text"}
    def no_gold(value):
        if isinstance(value, dict):
            assert not (banned & set(value))
            for item in value.values(): no_gold(item)
        elif isinstance(value, list):
            for item in value: no_gold(item)
    listed = client.get(BASE + "/practice/questions", headers=h1)
    assert listed.status_code == 200
    no_gold(listed.json())
    for qid in DEMO_IDS:
        item = client.get(BASE + "/practice/questions/" + qid, headers=h1)
        assert item.status_code == 200
        item = item.json()
        no_gold(item)
        grading = json.loads((ROOT / "data/clinical-cases/exercises/grading" / (qid + ".json")).read_text(encoding="utf-8"))
        for image in item["clinical_exercise"]["images"]:
            path = BASE + image["url"]
            assert client.get(path).status_code in (401, 403)
            response = client.get(path, headers=h1)
            assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
            expected = next(a for a in grading["assets"] if a["asset_id"] == image["asset_id"])
            assert hashlib.sha256(response.content).hexdigest() == expected["sha256"]
            assert expected["source_image_id"] not in response.headers.get("content-disposition", "")
        payload = {"question_id": qid, "student_answer": ANSWER}
        headers = {**h1, "Idempotency-Key": private["keys"][qid]}
        submitted = client.post(BASE + "/practice/attempts", headers=headers, json=payload)
        assert submitted.status_code == 200, submitted.status_code
        result = submitted.json()
        assert result["status"] == "completed" and result["execution_mode"] == "mock"
        assert result["student_answer"] == ANSWER and result["clinical_solution"]["criteria"]
        assert result["medical_evaluation"]["total_score"] == 0
        assert client.post(BASE + "/practice/attempts", headers=headers, json=payload).json()["id"] == result["id"]
        attempt_path = BASE + "/practice/attempts/" + result["id"]
        assert client.get(attempt_path, headers=h1).json()["id"] == result["id"]
        assert client.get(attempt_path, headers=h2).status_code == 404
        assert client.post(attempt_path + "/retry", headers=h2).status_code == 404
        for image in result["clinical_exercise"]["images"]:
            assert client.get(BASE + image["url"], headers=h2).status_code == 404
        attempts.append(result["id"])
        checks.append({"question_id": qid, "status": "completed", "execution_mode": "mock", "learner_payload_no_gold": True, "asset_bytes_verified": True, "ownership_denied_other_user": True, "idempotency_verified": True, "history_reload_verified": True})
    private["attempts"] = attempts
    PRIVATE.write_text(json.dumps(private), encoding="utf-8")
    output = ROOT / "data/clinical-cases/exercises/api-check.json"
    output.write_text(json.dumps({"checks": checks, "llm_calls": 0, "grading_quality_verified": False}, indent=2), encoding="utf-8")
    print(json.dumps({"real_local_API_checks": len(checks), "provider": "mock", "secrets_printed": False, "status": "passed"}))


if __name__ == "__main__":
    main()
