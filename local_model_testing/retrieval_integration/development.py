"""Source-checked development routing questions; no locked final benchmark is read."""

from .common import ROOT, RUN, CORPUS, read, rows, write
from app.ai.retrieval.evidence import content_hash


EMERGENCY = "SRC_ORTHO_EMERGENCY_001"
TEXTBOOK = "SRC_ORTHO_TEXTBOOK_001"
QUESTIONS = [
    (
        "ST_CLOSE",
        EMERGENCY,
        "Sau cắt lọc vết thương phần mềm, sách Cấp cứu ngoại khoa 2006 nêu hai vùng nào có thể khâu kín và ngoại lệ đối với vết cắn là gì?",
        [
            "DRN_0ca792732a665fcd8f8b6f5d6d190533",
            "DRN_c09359b7e3f55839bb56f6a309ab90a9",
        ],
    ),
    (
        "AMP_STUMP",
        EMERGENCY,
        "Trong chương Cắt cụt chi của sách 2006, xử trí đóng hay để hở mỏm cụt khác nhau thế nào giữa chi hoại tử nhiễm trùng và chi hỏng nhưng không nhiễm trùng?",
        [
            "DRN_266176afece6507a89a8a84bccbda752",
            "DRN_88f9cd65fbf05d87b07158c32ff625d8",
        ],
    ),
    (
        "FX_RADIO",
        TEXTBOOK,
        "Theo sách Bệnh học ngoại khoa chấn thương chỉnh hình 2021, phim X quang thường quy đánh giá gãy xương cần lấy những khớp nào và đủ những tư thế nào?",
        ["DRN_30e9720505045cc29ff514c9f0428558"],
    ),
    (
        "ST_DEEP",
        EMERGENCY,
        "Vết thương sâu qua cân đến cơ được chia thành những nhóm tổn thương cơ nào trong sách Cấp cứu ngoại khoa 2006?",
        ["DRN_6f30f127db1257069ec2048af6acda8a"],
    ),
    (
        "SKIN_GLOVE",
        EMERGENCY,
        "Sách Cấp cứu ngoại khoa 2006 mô tả cách xử trí lột da bàn tay kiểu lột găng như thế nào?",
        ["DRN_17d6e5b3f2af5ae9badaff24cbb77c63"],
    ),
    (
        "OPEN_DEFINITION",
        EMERGENCY,
        "Theo sách Cấp cứu ngoại khoa 2006, ổ gãy thông với môi trường ngoài qua đường nào để được gọi là gãy xương hở?",
        ["MC_485db981fe124da3a01227402f6e298c"],
    ),
    (
        "OPEN_SMALL",
        EMERGENCY,
        "Sách Cấp cứu ngoại khoa 2006 lưu ý điều gì về nguy cơ bỏ sót những gãy xương hở nhỏ?",
        ["MC_485db981fe124da3a01227402f6e298c"],
    ),
    (
        "AMP_GUILLOTINE",
        EMERGENCY,
        "Khi nào sách Cấp cứu ngoại khoa 2006 còn nêu việc cắt cụt nhanh kiểu khoanh giò để giải thoát người bị nạn?",
        ["DRN_73850fc10e2f5ec594ed14bf0f8a8824"],
    ),
    (
        "ST_AVULSION",
        EMERGENCY,
        "Với da bị lột rời, sách Cấp cứu ngoại khoa 2006 mô tả xử trí phần da đó như thế nào?",
        ["DRN_d0a61691572659d690d4b83becc32789"],
    ),
    (
        "FX_FATIGUE",
        TEXTBOOK,
        "Theo sách Bệnh học ngoại khoa 2021, gãy xương do mệt mỏi liên quan kiểu tác động lực nào và thường gặp ở đâu?",
        ["DRN_2a88eef5eb8954e1a371b875ea418f85"],
    ),
    (
        "FX_GREENSTICK",
        TEXTBOOK,
        "Sách Bệnh học ngoại khoa 2021 mô tả hai phía vỏ xương trong gãy cành tươi và kiểu di lệch như thế nào?",
        ["DRN_407da6569fae5c0c9fd778f22c11198c"],
    ),
    (
        "FX_CLOSED",
        TEXTBOOK,
        "Trong phân loại gãy xương của sách 2021, gãy kín được mô tả như thế nào?",
        ["DRN_6ba7a5e6299e57a2a6b08552156c88c7"],
    ),
    (
        "FX_INTERPOSITION",
        TEXTBOOK,
        "Chương đại cương gãy xương sách 2021 mô tả kẹt phần mềm làm nắn chỉnh kín thất bại như thế nào?",
        ["DRN_37e237e7bcd45131868370b1c841d867"],
    ),
    (
        "FX_CAST",
        TEXTBOOK,
        "Chèn ép do bột được mô tả trong phần biến chứng điều trị gãy xương của sách 2021 như thế nào?",
        ["DRN_5828060fb74f5022ab6a8e6761f3d1c7"],
    ),
    (
        "FX_DVT",
        TEXTBOOK,
        "Phần chăm sóc sau mổ gãy xương sách 2021 nêu dự phòng huyết khối tĩnh mạch sâu như thế nào?",
        ["DRN_4966627de21e5385902ff93d1a828ce5"],
    ),
]

MEDICAL = {
    "ST_CLOSE": {
        "criteria": [
            "Nêu đủ hai vùng: đầu mặt và bàn tay có thể khâu kín sau cắt lọc.",
            "Vết cắn do người hoặc súc vật luôn để hở theo đoạn nguồn.",
        ],
        "correct": "Sau cắt lọc có thể khâu kín vết thương ở đầu mặt và bàn tay. Ngoại lệ là vết cắn của người hoặc súc vật phải để hở.",
        "mixed": "Sau cắt lọc có thể khâu kín vết thương ở đầu mặt và bàn tay. Mọi vết cắn của người hoặc súc vật đều phải khâu kín ngay.",
        "vectors": {"correct": [1, 1], "mixed": [1, 0]},
    },
    "AMP_STUMP": {
        "criteria": [
            "Sau cắt cụt do chi hoại tử nhiễm trùng, để hở hoàn toàn đầu mỏm cụt.",
            "Chi hỏng không nhiễm trùng: có thể đóng kín mỏm cụt và dẫn lưu.",
        ],
        "correct": "Mỏm cụt của chi hoại tử nhiễm trùng được để hở hoàn toàn. Nếu chi hỏng nhưng không nhiễm trùng thì có thể đóng kín kèm dẫn lưu.",
        "mixed": "Mỏm cụt của chi hoại tử nhiễm trùng phải được đóng kín ngay. Nếu chi hỏng nhưng không nhiễm trùng thì có thể đóng kín kèm dẫn lưu.",
        "vectors": {"correct": [1, 1], "mixed": [0, 1]},
    },
    "FX_RADIO": {
        "criteria": [
            "Phim phải lấy hết khớp trên và khớp dưới ổ gãy.",
            "Có đủ hai tư thế: thẳng và nghiêng.",
        ],
        "correct": "Phim cần bao gồm trọn cả khớp ở phía trên lẫn khớp ở phía dưới ổ gãy, với hai tư thế thẳng và nghiêng.",
        "mixed": "Chỉ lấy đúng ổ gãy, không được đưa khớp trên hay khớp dưới vào phim. Hai tư thế cần có là thẳng và nghiêng.",
        "vectors": {"correct": [1, 1], "mixed": [0, 1]},
    },
}


def main():
    if (RUN / "experiment-manifest.json").exists():
        for name, sha in read(RUN / "experiment-manifest.json")["files"].items():
            from .common import file_hash

            assert file_hash(ROOT / name) == sha
        print("Frozen development supplement reused; no labels or input changed")
        return
    # Source identity/locators are copied from accepted graph exports, not model answers.
    nodes = {}
    graph_files = [
        ROOT
        / "data/knowledge-extraction/v2/source-review-20261102/combined/graph.json",
        ROOT
        / "data/knowledge-extraction/v2/source-review-20261102-2021-completion/combined/graph.json",
    ]
    for p in graph_files:
        nodes.update({n["id"]: n for n in read(p)["nodes"]})
    corpus = rows(CORPUS / "corpus.jsonl")
    mapping = {
        "version": "book-question-concept-v1-20261111",
        "link_method": "manual source/locator verification, not fuzzy names or course inference",
        "questions": {},
    }
    development = []
    medical = []
    for short, source_id, question, ids in QUESTIONS:
        qid = "KGR_DEV_" + short
        verified = []
        for nid in ids:
            node = nodes[nid]
            sources = [
                s
                for c in node["content"]
                for s in c["sources"]
                if s["source_id"] == source_id
            ]
            assert sources
            for s in sources:
                # Exact page-text source resolution (including windows joined at overlap).
                pages = sorted({s["pdf_pages"][0]})
                chunks = sorted(
                    (
                        c
                        for c in corpus
                        if c["source_id"] == source_id
                        and c["page"] in pages
                        and c.get("start") is not None
                    ),
                    key=lambda c: c["start"],
                )
                text = ""
                for c in chunks:
                    if c["start"] <= len(text):
                        text += c["content"][max(0, len(text) - c["start"]) :]
                assert " ".join(s["excerpt"].split()) in " ".join(text.split()), (
                    qid,
                    nid,
                )
                verified.append({"node_id": nid, "node_name": node.get("name"), **s})
        mapping["questions"][qid] = {
            "question_sha256": content_hash(question),
            "concept_ids": ids,
            "source_ids": [source_id],
            "review_status": "Codex source checked; not clinician approved",
            "verification": verified,
        }
        development.append(
            {
                "question_id": qid,
                "question": question,
                "source_id": source_id,
                "concept_ids": ids,
                "split": "development",
                "new_medical": short in MEDICAL,
            }
        )
        if short in MEDICAL:
            spec = MEDICAL[short]
            rubric = {
                "schema_version": "1.0.0",
                "rubric_id": qid + "_R1",
                "question_id": qid,
                "course_id": None,
                "topic_id": None,
                "scoring_rule": "two independent 1-point criteria",
                "validation_status": "agent_source_checked",
                "expert_review_required": True,
                "expert_review_reason": "Reference not independently clinically adjudicated",
                "max_score": 2.0,
                "criteria": [
                    {
                        "criterion_id": qid + "_C" + str(i + 1),
                        "description": text,
                        "max_score": 1.0,
                        "required_source_unit_ids": [],
                        "acceptable_variants": [],
                        "common_incorrect_claims": [],
                    }
                    for i, text in enumerate(spec["criteria"])
                ],
            }
            medical.append(
                {
                    "question_id": qid,
                    "question": question,
                    "rubric": rubric,
                    "answers": [
                        {
                            "sample_id": qid + "__" + kind,
                            "student_answer": spec[kind],
                            "expected_vector": spec["vectors"][kind],
                        }
                        for kind in ("correct", "mixed")
                    ],
                    "source_reference": verified,
                    "user_reviewed": False,
                    "clinician_approved": False,
                }
            )
    # Existing book-derived application question: one explicit source-checked registry entry.
    initial = read(RUN / "baseline.json")["runtime_audit"]["questions"]
    for q in initial:
        if q["id"] == "ORTHO_B21CN1_Q_0001":
            mapping["questions"][q["id"]] = {
                "question_sha256": content_hash(q["question"]),
                "concept_ids": ["MC_485db981fe124da3a01227402f6e298c"],
                "source_ids": [EMERGENCY],
                "verification": [
                    {
                        "basis": "Existing integration source-unit definition and node exact same textbook passage",
                        "source_id": EMERGENCY,
                        "pdf_page": 16,
                    }
                ],
            }
    for name, value in (
        ("development-questions.json", development),
        ("medical-development.json", medical),
    ):
        write(RUN / name, value)
    write(ROOT / "apps/backend/app/ai/retrieval/book_mapping.v1.json", mapping)
    write(
        RUN / "pre-model-configuration.json",
        {
            "parent_benchmark": "benchmark-v1-20261110",
            "max_attempts": 12,
            "shared_total": 800,
            "medical_model_unchanged": True,
            "smoke_calls": 0,
            "generation": {
                "max_new_tokens": 1200,
                "seed": 42,
                "do_sample": False,
                "input_limit": 4096,
            },
            "retrieval": {
                "encoder": read(CORPUS / "index-manifest.json")["encoder"],
                "top_k": 3,
                "context_chars": 6000,
                "min_similarity": 0.75,
                "hybrid_weights": [0.85, 0.15],
                "max_hops": 1,
            },
            "query_inputs": "question + curated question/concept/source mapping only; not student/rubric/expected",
        },
    )
    print("Prepared15 development questions,3Medical pairs; no generation")


if __name__ == "__main__":
    main()
