"""Read-only empty-input rejection against the existing web API. No benchmark attempt write."""
import json

import httpx

from .common import ROOT, RUN, read, write


def main():
    users = read(ROOT / "data/backups/clinical-demo-accounts.json")["users"]
    with httpx.Client(base_url="http://127.0.0.1:8000/api/v1", timeout=10) as client:
        response = client.post("/auth/login", json={k: users[0][k] for k in ("email", "password")})
        assert response.status_code == 200
        header = {"Authorization": "Bearer " + response.json()["access_token"],
                  "Idempotency-Key": "benchmark-empty-rejection-only-20261110"}
        cfg = client.get("/practice/config", headers=header).json()
        result = client.post("/practice/attempts", headers=header,
            json={"question_id": "ORTHO_B21CN1_Q_0001", "student_answer": ""})
        assert result.status_code == 422
        report = {"http_status": 422, "error": result.json(), "generation_calls": 0,
                  "scope": "existing app empty-input validation only, not model HTTP integration",
                  "provider_mode_unchanged": cfg["execution_mode"]}
        write(RUN / "empty-api-rejection.json", report)
        print(json.dumps({"http_status": 422, "generation_calls": 0,
                          "model_http_integration": "not_run"}))


if __name__ == "__main__":
    main()
