"""Create isolated demo identities and source-linked, explicitly simulated study history.

No LLM, graph writes, fabricated grades, account promotion, or existing-user reset.
Run again to verify the same accounts without replacing subsequent demo activity.
"""

import asyncio
import json
import os
import secrets
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/demo-accounts/demo-20261112"
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
PROFILES = [
    {"key": "moi", "name": "Demo — Mới bắt đầu", "read": 0, "reading": 0, "bookmarked": 0, "submitted": 0, "drafts": 0, "notes": 0},
    {"key": "coban", "name": "Demo — Làm quen", "read": 8, "reading": 2, "bookmarked": 3, "submitted": 1, "drafts": 1, "notes": 3},
    {"key": "danghoc", "name": "Demo — Đang học", "read": 25, "reading": 4, "bookmarked": 8, "submitted": 4, "drafts": 2, "notes": 7},
    {"key": "ontap", "name": "Demo — Ôn tập", "read": 60, "reading": 6, "bookmarked": 12, "submitted": 10, "drafts": 2, "notes": 12},
    {"key": "admin", "name": "Demo — Quản trị viên", "read": 0, "reading": 0, "bookmarked": 0, "submitted": 0, "drafts": 0, "notes": 0},
]


async def inside():
    import app.models  # noqa: F401
    import httpx
    from sqlalchemy import select
    from app.common.enums import UserRole
    from app.core.database import SessionFactory
    from app.core.security import hash_password, verify_password
    from app.modules.knowledge.service import get_graph_store
    from app.modules.study.models import StudyRecord, StudySession
    from app.modules.study.questions import question_bank
    from app.modules.users.models import User

    RUN.mkdir(parents=True, exist_ok=True)
    private_path = RUN / "accounts.private.json"
    if private_path.exists():
        private = json.loads(private_path.read_text(encoding="utf-8"))
    else:
        store = get_graph_store()
        try:
            snapshot = await store.snapshot()
        finally:
            await store.close()
        clinical = [n for n in snapshot.nodes.values() if not n["curricular"] and n["content"] and n["type"] in {"Condition", "Finding", "Classification", "DiagnosticMethod", "Intervention", "ClinicalPrinciple", "Skill", "Anatomy"}]
        # Round-robin source chapters rather than filling every profile with chapter one.
        groups = {}
        for node in sorted(clinical, key=lambda n: (n["title"], n["id"])):
            chapter = node["chapters"][0] if node["chapters"] else {"source_id": node["book_ids"][0], "number": 0}
            groups.setdefault((chapter["source_id"], chapter["number"]), []).append(node)
        ordered = []
        while any(groups.values()) and len(ordered) < 66:
            for key in sorted(groups):
                if groups[key]:
                    ordered.append(groups[key].pop(0))
                if len(ordered) == 66:
                    break
        if len(ordered) < 66:
            raise RuntimeError("Insufficient source-backed reading nodes; no accounts created")
        bank = question_bank(snapshot)
        questions = [q for q in bank.values() if q.get("origin") == "kg_template" and q.get("task") == "source_recall" and set(q["node_ids"]) & {n["id"] for n in ordered}]
        questions.sort(key=lambda q: (q["book_ids"], q["id"]))
        if len(questions) < 36:
            raise RuntimeError("Insufficient source-backed self-study questions")
        password = "Demo!" + secrets.token_urlsafe(10)
        private = {"created_at": datetime.now(UTC).isoformat(), "label": "synthetic_demo_not_assessed", "password": password, "accounts": []}
        emails = ["demo." + p["key"] + "@example.com" for p in PROFILES]
        now = datetime.now(UTC)
        async with SessionFactory() as session, session.begin():
            conflicts = list(await session.scalars(select(User.email).where(User.email.in_(emails))))
            if conflicts:
                raise RuntimeError("Demo email collision; refusing to reset or overwrite existing users")
            for profile, email in zip(PROFILES, emails, strict=True):
                user = User(email=email, full_name=profile["name"], hashed_password=hash_password(password),
                            role=UserRole.ADMIN if profile["key"] == "admin" else UserRole.LEARNER, is_active=True)
                session.add(user)
                await session.flush()
                detail = {**profile, "email": email, "user_id": str(user.id), "role": user.role.value, "reading_records": [], "sessions": []}
                studied_ids = {n["id"] for n in ordered[:profile["read"] + profile["reading"]]}
                profile_questions = [q for q in questions if set(q["node_ids"]) & studied_ids]
                if len(profile_questions) < 3 * (profile["submitted"] + profile["drafts"]):
                    raise RuntimeError("Insufficient questions for this profile's reading selection")
                for i, node in enumerate(ordered[:profile["read"] + profile["reading"]]):
                    state = "read" if i < profile["read"] else "reading"
                    stamp = now - timedelta(days=(profile["read"] + profile["reading"] - i) // 3, hours=i % 4)
                    note = "[DỮ LIỆU DEMO MÔ PHỎNG] Đã lưu mục để đối chiếu nguồn và ôn lại; không phải đánh giá năng lực." if i < profile["notes"] else ""
                    session.add(StudyRecord(user_id=user.id, node_id=node["id"], title=node["title"],
                        read_state=state, bookmarked=i < profile["bookmarked"], note=note,
                        revision=node["revision"], version=1, created_at=stamp, updated_at=stamp))
                    detail["reading_records"].append({"node_id": node["id"], "title": node["title"], "state": state,
                        "bookmarked": i < profile["bookmarked"], "note": note, "sources": node["sources"], "chapters": node["chapters"]})
                for i in range(profile["submitted"] + profile["drafts"]):
                    chosen = profile_questions[i * 3:i * 3 + 3]
                    finished = i < profile["submitted"]
                    answers = {q["id"]: "[DỮ LIỆU DEMO MÔ PHỎNG] Câu trả lời mẫu để trình diễn lưu bài và tiến độ. Chưa đánh giá kiến thức hoặc năng lực." for q in (chosen if finished else chosen[:1])}
                    import hashlib
                    import uuid
                    question_ids = [q["id"] for q in chosen]
                    stamp = now - timedelta(days=(profile["submitted"] + profile["drafts"] - i), minutes=15)
                    row = StudySession(user_id=user.id, idempotency_key=str(uuid.uuid4()),
                        input_hash=hashlib.sha256(json.dumps(question_ids).encode()).hexdigest(),
                        status="submitted" if finished else "draft", questions=chosen, answers=answers,
                        version=1, created_at=stamp, updated_at=stamp)
                    session.add(row)
                    await session.flush()
                    detail["sessions"].append({"id": str(row.id), "status": row.status, "question_count": len(chosen), "answered_count": len(answers)})
                private["accounts"].append(detail)
            # Keep recoverable login information local, never in source or terminal output.
            private_path.write_text(json.dumps(private, ensure_ascii=False, indent=2), encoding="utf-8")

    results = []
    async with httpx.AsyncClient(base_url="http://medresident-tutor-backend-1:8000/api/v1", timeout=60, trust_env=False) as client:
        for item in private["accounts"]:
            async with SessionFactory() as session:
                user = await session.scalar(select(User).where(User.email == item["email"]))
                assert user and str(user.id) == item["user_id"]
                assert user.hashed_password != private["password"] and verify_password(private["password"], user.hashed_password)
            response = await client.post("/auth/login", json={"email": item["email"], "password": private["password"]})
            assert response.status_code == 200, "Demo login failed"
            headers = {"Authorization": "Bearer " + response.json()["access_token"]}
            response = await client.get("/study/summary", headers=headers)
            assert response.status_code == 200
            summary = response.json()
            for key in ("read", "reading", "bookmarked", "submitted", "drafts"):
                assert summary[key] == item[key], "Demo activity differs from initial manifest; refusing to reset it"
            assert summary["mastery_assessed"] is False
            sessions_response = await client.get("/study/sessions?limit=100", headers=headers)
            assert sessions_response.status_code == 200
            assert sessions_response.json()["total"] == item["submitted"] + item["drafts"]
            admin_response = await client.get("/admin/questions?limit=1", headers=headers)
            assert admin_response.status_code == (200 if item["role"] == "ADMIN" else 403)
            if item["sessions"]:
                another = private["accounts"][0]
                outsider = await client.post("/auth/login", json={"email": another["email"], "password": private["password"]})
                isolated = await client.get("/study/sessions/" + item["sessions"][0]["id"], headers={"Authorization": "Bearer " + outsider.json()["access_token"]})
                assert isolated.status_code == 404
            results.append({"email": item["email"], "name": item["name"], "role": item["role"],
                "summary": summary, "notes": item["notes"], "login_verified": True, "hashed_password_verified": True,
                "role_verified": True, "session_ownership_verified": True})
    (RUN / "verification.json").write_text(json.dumps({"accounts": results, "llm_calls": 0,
        "grades_created": 0, "neo4j_writes": 0, "activity_kind": "synthetic_demo_ungraded"}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Tài khoản demo local", "", "Dữ liệu hoạt động mô phỏng. Bài tự luyện chưa chấm; không phải mức thành thạo hay tỷ lệ hoàn thành chương trình.",
             "", "Đăng nhập: http://localhost:3000/login", "", "Mật khẩu chung: " + private["password"], "",
             "| Tài khoản | Vai trò | Đã đọc | Đang đọc | Dấu trang | Bài hoàn tất | Bài nháp | Ghi chú |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for a in private["accounts"]:
        lines.append(f"| {a['email']} | {a['role']} | {a['read']} | {a['reading']} | {a['bookmarked']} | {a['submitted']} | {a['drafts']} | {a['notes']} |")
    lines += ["", "Mở /dashboard xem tổng quan; /progress xem ghi chú, dấu trang và bài tự luyện; /exams mở bài nháp hoặc đã hoàn tất. Tài khoản admin có thêm /admin/questions.",
              "", "Mỗi bài gồm 3 câu nguồn thật: bài hoàn tất có 3/3 câu trả lời mô phỏng; bài nháp có 1/3. Nội dung và ngày hoạt động được tạo để demo. Không có điểm AI hoặc chứng nhận hoàn thành môn."]
    for a in private["accounts"]:
        lines += ["", "## " + a["name"] + " — " + a["email"], ""]
        lines += [f"- {r['state']}: {r['title']}" for r in a["reading_records"]]
        lines += [f"- Bài {s['status']}: http://localhost:3000/exams?session={s['id']} ({s['answered_count']}/{s['question_count']} câu)" for s in a["sessions"]]
    (RUN / "accounts.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"accounts_verified": len(results), "passwords_printed": False, "llm_calls": 0,
        "profiles": [{"email": r["email"], "role": r["role"], **{k: r["summary"][k] for k in ("read", "reading", "bookmarked", "submitted", "drafts")}} for r in results]}))


def main():
    if "--inside" in sys.argv:
        return asyncio.run(inside())
    inspected = json.loads(subprocess.check_output([DOCKER, "inspect", "medresident-tutor-backend-1"], text=True))[0]
    env = dict(e.split("=", 1) for e in inspected["Config"]["Env"])
    env["PYTHONPATH"] = "/workspace:/workspace/apps/backend:/workspace/model-training:/usr/local/lib/python3.12/site-packages"
    env["KNOWLEDGE_DATA_ROOT"] = "/workspace/data"
    network = next(iter(inspected["NetworkSettings"]["Networks"]))
    cmd = [DOCKER, "run", "--rm", "--name", "medresident-demo-accounts", "--network", network,
        "--mount", f"type=bind,source={ROOT},target=/workspace", "-w", "/workspace"]
    for key in env:
        cmd.extend(["-e", key])
    cmd.extend(["medresident-tutor-backend:latest", "python", "-m", "local_model_testing.demo_accounts", "--inside"])
    result = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True)
    out = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    for key, value in env.items():
        if value and any(k in key for k in ("PASSWORD", "SECRET", "KEY", "URL")):
            out = out.replace(value, "[REDACTED]")
    RUN.mkdir(parents=True, exist_ok=True)
    (RUN / "seed.log").write_text(out, encoding="utf-8")
    print(out[-3500:].encode("ascii", "backslashreplace").decode())
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
