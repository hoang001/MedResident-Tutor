"""Synthetic graph fixture. Never imported by the production application."""

from app.modules.knowledge.service import PROGRAM, Snapshot

SOURCE = "SRC_ORTHO_TEXTBOOK_001"
ROOT = f"CURRICULUM:{PROGRAM}"
COURSE = f"{ROOT}:COURSE:B21CN1"
FOCUS_COURSE = f"{ROOT}:COURSE:B21CN7"
ITEM = "FIXTURE:CONDITION"
QUESTION = "FIXTURE:QUESTION"


def make_snapshot(root=None):
    ref = {
        "source_id": SOURCE,
        "pdf_pages": [8],
        "printed_pages": [],
        "excerpt": "Synthetic fixture: not medical teaching content.",
    }
    nodes = [
        {
            "labels": ["MedicalConcept", "Condition"],
            "p": {
                "id": ITEM,
                "name": "Trật khớp vai — dữ liệu thử giao diện",
                "content": [
                    {"text": "Nội dung thử nghiệm, không dùng học y khoa.", "sources": [ref]}
                ],
            },
        },
        {
            "labels": ["SampleQuestion"],
            "p": {
                "id": QUESTION,
                "text": "Câu hỏi thử giao diện: bạn đã đọc trích dẫn chưa?",
                "sources": [ref],
                "answer": "DO NOT EXPOSE GOLD ANSWER",
            },
        },
        {
            "labels": ["MedicalConcept", "Condition"],
            "p": {
                "id": "FIXTURE:UNRELATED",
                "name": "Unrelated graph node",
                "sources": [{"source_id": "PRIVATE_OTHER_SOURCE", "pdf_pages": [1]}],
            },
        },
        {
            "labels": ["Curriculum", "CurriculumEntity"],
            "p": {
                "id": ROOT,
                "curriculum_id": PROGRAM,
                "name": "Chương trình thử giao diện",
            },
        },
        {
            "labels": ["CurriculumGroup", "CurriculumEntity"],
            "p": {
                "id": ROOT + ":GROUP",
                "curriculum_id": PROGRAM,
                "name": "Chuyên ngành",
            },
        },
        {
            "labels": ["Course", "CurriculumEntity"],
            "p": {
                "id": COURSE,
                "curriculum_id": PROGRAM,
                "name": "Nền tảng thử giao diện",
                "course_code": "B21CN1",
                "content_status": "awaiting_teacher_content",
                "hmu_course_url": "https://lms.hmu.edu.vn/course/view.php?id=1",
            },
        },
        {
            "labels": ["Course", "CurriculumEntity"],
            "p": {
                "id": FOCUS_COURSE,
                "curriculum_id": PROGRAM,
                "name": "Học phần thử giao diện",
                "course_code": "B21CN7",
                "round": 2,
                "year": 2,
                "total_credits": 6,
                "content_status": "awaiting_teacher_content",
            },
        },
    ]
    edges = [
        {"start": ROOT, "end": ROOT + ":GROUP", "type": "HAS_GROUP", "p": {}},
        {"start": ROOT + ":GROUP", "end": COURSE, "type": "HAS_COURSE", "p": {}},
        {"start": ROOT + ":GROUP", "end": FOCUS_COURSE, "type": "HAS_COURSE", "p": {}},
        {"start": QUESTION, "end": ITEM, "type": "ABOUT", "p": {"sources": [ref]}},
    ]
    catalog = {
        "books": [
            {
                "id": SOURCE,
                "title": "Sách dùng trong kiểm thử",
                "year": 2021,
                "pages": 532,
                "sha256": "0" * 64,
                "filename": "DVC.005844.pdf",
                "chapters": [
                    {
                        "number": 1,
                        "title": "Bài thử giao diện",
                        "start": 8,
                        "end": 22,
                        "opening_missing": False,
                    }
                ],
            }
        ]
    }
    return Snapshot(nodes, edges, catalog, {"courses": []})


class FixtureStore:
    def __init__(self):
        self.value = make_snapshot()

    async def snapshot(self):
        return self.value

    async def close(self):
        pass
