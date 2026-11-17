"""Build and freeze a new benchmark from manually authored, local-source claims."""
import copy
import difflib
import json
import re
from datetime import UTC, datetime

from .authoring import MANUAL, TOPICS
from .common import DATA, ROOT, RUN, file_hash, fingerprint, jsonl, read, write

BOOKS = {"2006": ("SRC_ORTHO_EMERGENCY_001", "Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi"),
         "2021": ("SRC_ORTHO_TEXTBOOK_001", "DVC.005844")}
OFF_TOPIC = [
    "Cuối tuần tôi muốn đi nghe nhạc ở công viên.", "Tôi đang chọn màu sơn xanh cho căn phòng.",
    "Tối nay tôi dự định nấu cơm và xem một bộ phim.", "Chiếc xe đạp của tôi cần bơm thêm hơi.",
    "Tôi thích chụp ảnh phong cảnh lúc bình minh.", "Nhà tôi vừa trồng thêm một cây hoa giấy.",
    "Tôi muốn tìm một cuốn tiểu thuyết để đọc trong kỳ nghỉ.", "Ngày mai tôi sẽ đi tàu về thăm quê.",
    "Chiếc bàn gỗ trong phòng khách hơi nhỏ.", "Tôi thích học đàn piano vào tối thứ bảy.",
]


def norm(text):
    return re.sub(r"\W+", " ", text.casefold()).strip()


def prepare():
    if (DATA / "manifest.json").exists():
        raise RuntimeError("Dataset already frozen; use a new revision directory")
    sources, pages, corpus = {}, {}, []
    catalog = read(ROOT / "data/library/catalog.json")["books"]
    for year, (sid, filename) in BOOKS.items():
        path = ROOT / "data/graduate" / (filename + ".json")
        source = read(path)
        sources[year] = {"source_id": sid, "ocr_path": path.relative_to(ROOT).as_posix(),
                         "ocr_sha256": file_hash(path), "pdf_sha256": source["source_sha256"]}
        pages[year] = {s["page_start"]: s["text"] for s in source["sections"]}
        book = next(b for b in catalog if b["id"] == sid)
        for page, text in pages[year].items():
            chapter = next((c["title"] for c in book["chapters"] if c["start"] <= page <= c["end"]), "")
            # Full corpus from books only. No authored questions/answers/reference rows.
            for start in range(0, len(text), 900):
                content = text[start:start + 1800]
                if len(content.strip()) < 80:
                    continue
                corpus.append({"chunk_id": f"OCR_{year}_{page}_{start}", "source_id": sid,
                               "page": page, "start": start, "end": start + len(content),
                               "chapter": chapter, "content": content, "origin": "original_ocr"})
    questions, samples, references, provenance = [], [], [], []
    manual_units = []
    for topic_index, (topic, year, split, entries) in enumerate(TOPICS):
        for number, (page, anchor, question, task, canonical, paraphrases, wrong) in enumerate(entries, 1):
            qid = f"MRB1_{topic_index + 1:02}_{number:02}"
            text = pages[year][page]
            if anchor.startswith("MANUAL:"):
                key = anchor.split(":", 1)[1]
                excerpt = MANUAL[(year, key)]
                unit = f"PDF_{year}_{page}_" + fingerprint(excerpt)[:12]
                start, end = None, None
                origin = "agent_manual_pdf_transcription"
                manual_units.append({"chunk_id": unit, "source_id": BOOKS[year][0], "page": page,
                    "start": None, "end": None, "chapter": topic, "content": excerpt,
                    "origin": origin})
            else:
                start = text.index(anchor)
                excerpt = text[start:start + 1800]
                end = start + len(excerpt)
                unit = f"REF_{year}_{page}_{start}"
                origin = "verbatim_ocr_source_window"
            evidence = [{"source_unit_id": unit, "source_id": BOOKS[year][0], "title": topic,
                         "page_start": page, "page_end": page, "content": excerpt}]
            criteria = [{"criterion_id": qid + f"_C{i+1}",
                "description": claim + ". Cho 1 điểm khi đủ toàn ý; sai hoặc chưa nêu đủ cho 0.",
                "max_score": 1.0, "required_source_unit_ids": [unit]}
                for i, claim in enumerate(canonical)]
            rubric = {"rubric_id": qid + "_R", "question_id": qid, "max_score": 2.0,
                      "scoring_rule": "sum; each criterion all-or-none 0 or 1", "criteria": criteria}
            question_row = {"question_id": qid, "topic": topic, "book": year, "task": task,
                "split": split, "group_id": topic, "question": question, "rubric": rubric,
                "evidence": evidence, "review": "agent_source_checked",
                "user_reviewed": False, "clinician_approved": False}
            questions.append(question_row)
            provenance.append({"question_id": qid, **sources[year], "pdf_page": page,
                "source_window_start": start, "source_window_end": end, "text_origin": origin,
                "evidence_sha256": fingerprint(excerpt), "original_excerpt": excerpt,
                "criterion_support": {c["criterion_id"]: [unit] for c in criteria},
                "equivalence_policy": "Both criteria require the complete selected source passage; conservative full-span coverage, not semantic relevance adjudication"})
            # Distinct manually authored paraphrases and counterclaims, not model labels.
            # A wrong assertion is addressed-but-incorrect, not simultaneously 'missing'.
            variants = [
                ("full", " ".join(paraphrases), [1, 1], paraphrases, [], []),
                ("partial", paraphrases[0], [1, 0], [paraphrases[0]], [], [canonical[1]]),
                ("wrong", wrong[0], [0, 0], [], [wrong[0]], [canonical[1]]),
                ("mixed", paraphrases[0] + " " + wrong[1], [1, 0], [paraphrases[0]], [wrong[1]], []),
                ("unrelated", OFF_TOPIC[(topic_index + number) % len(OFF_TOPIC)], [0, 0], [], [], canonical),
            ]
            for kind, answer, scores, correct, incorrect, missing in variants:
                sample_id = qid + "__" + kind
                payload = {"question": question, "student_answer": answer,
                           "rubric": rubric, "evidence": evidence}
                samples.append({"sample_id": sample_id, "question_id": qid, "topic": topic,
                                "answer_type": kind, "split": split, "payload": payload})
                expected = {"correct_points": correct, "incorrect_points": incorrect,
                    "missing_points": missing,
                    "rubric_scores": [{"criterion_id": c["criterion_id"], "criterion": c["description"],
                        "score": float(score), "max_score": 1.0,
                        "reason": "Source-checked authored claim assignment; no model used"}
                        for c, score in zip(criteria, scores, strict=True)],
                    "total_score": float(sum(scores)), "max_score": 2.0,
                    "sufficient_evidence": True, "evidence_refs": [unit]}
                wrong_ids = ([criteria[0]["criterion_id"]] if kind == "wrong" else
                             [criteria[1]["criterion_id"]] if kind == "mixed" else [])
                references.append({"sample_id": sample_id, "expected": expected,
                    "explicitly_wrong_criteria": wrong_ids,
                    "label_reason": {"full": "Both paraphrased claims supported",
                        "partial": "First criterion supported; second not addressed",
                        "wrong": "First criterion explicitly contradicted; second absent",
                        "mixed": "First supported; second explicitly contradicted",
                        "unrelated": "No medical claim; both rubric points absent; preferences not false medical claims"}[kind],
                    "review": "agent_source_checked", "user_reviewed": False,
                    "clinician_approved": False})
    corpus.extend(manual_units)
    jsonl(DATA / "questions.jsonl", questions)
    jsonl(DATA / "medical-inputs.jsonl", samples)
    jsonl(DATA / "medical-reference.jsonl", references)
    jsonl(DATA / "provenance.jsonl", provenance)
    jsonl(DATA / "corpus.jsonl", corpus)
    # Frozen graph export copies: book-source knowledge only, no benchmark answers.
    graph_paths = ["data/knowledge-extraction/v2/source-review-20261102/combined/graph.json",
        "data/knowledge-extraction/v2/source-review-20261102-2021-completion/combined/graph.json"]
    graph = {"nodes": [], "edges": [], "source_files": []}
    for path in graph_paths:
        g = read(ROOT / path)
        graph["nodes"].extend(g["nodes"])
        graph["edges"].extend(g["edges"])
        graph["source_files"].append({"path": path, "sha256": file_hash(ROOT / path)})
    write(DATA / "graph-snapshot.json", graph)
    ref_by_id = {r["sample_id"]: r for r in references}
    test_questions = [q for q in questions if q["split"] == "test"]
    teaching, teaching_ref = [], []
    for index, q in enumerate(test_questions[::2]):
        kind = "partial" if index % 2 == 0 else "mixed"
        base_id = q["question_id"] + "__" + kind
        med = ref_by_id[base_id]["expected"]
        answer = next(s["payload"]["student_answer"] for s in samples if s["sample_id"] == base_id)
        for context in ("none", "recurring", "improving"):
            lc = {"mastery": [], "recurring_errors": [], "recent_improvements": [],
                  "recent_attempts_summary": None}
            if context == "recurring":
                anchor = (med["incorrect_points"] or med["missing_points"])[0]
                lc["recurring_errors"] = [{"error_summary": anchor, "count": 2}]
                lc["recent_attempts_summary"] = "Fixture: cùng lỗi này được ghi ở hai lượt trước."
            if context == "improving":
                lc["recent_improvements"] = [{"improvement_summary": med["correct_points"][0], "count": 2}]
                lc["recent_attempts_summary"] = "Fixture: hai lượt gần đây đã nêu đúng ý này."
            sid = q["question_id"] + "__teaching_" + context
            payload = {"schema_version": "1.0.0", "question": q["question"], "student_answer": answer,
                "medical_evaluation": copy.deepcopy(med), "learner_context": lc,
                "metadata": {"specialty": None, "course_group": None, "course_id": None,
                    "course_name": None, "specialty_level": None, "topic_id": None,
                    "topic_name": None, "concept_ids": []}}
            teaching.append({"sample_id": sid, "question_id": q["question_id"], "topic": q["topic"],
                             "split": "test", "context_type": context, "payload": payload})
            teaching_ref.append({"sample_id": sid, "origin": "synthetic_controlled_fixture",
                "medical_reference_sample_id": base_id, "medical_hash": fingerprint(med),
                "context_is_simulated": True, "review": "agent_source_checked_not_clinician"})
    # Separate Teaching smoke/development fixtures, from development-only topics.
    for index, q in enumerate([q for q in questions if q["split"] == "development"][::5]):
        base_id = q["question_id"] + "__partial"
        fixture = copy.deepcopy(teaching[0])
        fixture.update(sample_id=q["question_id"] + "__teaching_dev", question_id=q["question_id"],
                       topic=q["topic"], split="development", context_type="none")
        fixture["payload"].update(question=q["question"],
            student_answer=next(s["payload"]["student_answer"] for s in samples if s["sample_id"] == base_id),
            medical_evaluation=ref_by_id[base_id]["expected"],
            learner_context={"mastery": [], "recurring_errors": [], "recent_improvements": [],
                             "recent_attempts_summary": None})
        teaching.append(fixture)
    jsonl(DATA / "teaching-inputs.jsonl", teaching)
    jsonl(DATA / "teaching-reference.jsonl", teaching_ref)
    # Diagnostics on all locally available training/validation/test text, never edit it.
    training_questions = []
    for path in (ROOT / "data/training").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            text = r.get("question") or r.get("input", {}).get("question", "")
            if text:
                training_questions.append((path.relative_to(ROOT).as_posix(), r.get("sample_id"), text))
    leakage = []
    for q in questions:
        ranked = sorted(((difflib.SequenceMatcher(None, norm(q["question"]), norm(t)).ratio(), p, sid, t)
                         for p, sid, t in training_questions), reverse=True)
        score, p, sid, text = ranked[0]
        leakage.append({"question_id": q["question_id"], "max_question_sequence_similarity": score,
                        "closest_file": p, "closest_id": sid, "closest_question": text,
                        "exact_duplicate": norm(q["question"]) == norm(text)})
    if any(r["exact_duplicate"] for r in leakage):
        raise ValueError("Exact training duplicate requires regrouping before freezing")
    write(DATA / "leakage-audit.json", {"method": "normalized text exact + SequenceMatcher; not proof of absence of paraphrase contamination",
        "available_files": {str(p.relative_to(ROOT)): file_hash(p) for p in (ROOT / "data/training").glob("*.jsonl")},
        "adapter_training_provenance_incomplete": True, "rows": leakage})
    write(DATA / "review-queue.json", {"excluded_topics_or_passages": [
        {"book": "2006", "pages": [12, 13, 14, 15], "reason": "OCR alters growth-plate/anatomical terms; childhood fracture chapter not used"},
        {"book": "2021", "pages": [459, 460, 461], "reason": "OCR repeatedly replaces femur with generic long bone; femoral-shaft topic replaced by osteomyelitis"},
        {"book": "2021", "page": 103, "reason": "Toxin-name/mechanism OCR ambiguity; no toxin-name question authored"},
        {"book": "2021", "page": 112, "reason": "Inconsistent percentage enumeration; incidence/percentage questions excluded"}],
        "manual_pdf_transcriptions_checked_by_agent": {"2006": [46, 48], "2021": [496]},
        "user_reviewed": False, "clinician_approved": False,
        "pending": ["Clinical correctness/translation and synthetic distractors", "All selected excerpts", "Conservative retrieval qrels"]})
    write(DATA / "policy.json", {"correct_points": "Claims actually stated and source-supported",
        "incorrect_points": "Claims actually stated and source-refuted; unrelated preferences never counted as incorrect",
        "missing_points": "Unaddressed required criteria; explicitly wrong addressed criterion not double-listed as missing",
        "sufficient_evidence": "Enough reference source to grade, independent of student correctness",
        "review_level": "agent_source_checked; not user or clinician approval"})
    review_ids = [q["question_id"] + "__" + ["full", "partial", "wrong", "mixed", "unrelated"][i % 5]
                  for i, q in enumerate(test_questions)]
    write(DATA / "split.json", {"unit": "topic/chapter group", "development_topics": [t[0] for t in TOPICS if t[2] == "development"],
        "test_topics": [t[0] for t in TOPICS if t[2] == "test"], "medical_review_sample_ids": review_ids,
        "teaching_review_sample_ids": [r["sample_id"] for r in teaching if r["split"] == "test"][::5],
        "medical_dev_smoke_ids": ["MRB1_01_01__full", "MRB1_01_05__unrelated", "MRB1_02_02__mixed", "MRB1_02_04__partial"]})
    write(DATA / "experiment.json", {"batch_size": 1, "shard_size": 25, "seed": 42,
        "configurations": ["medical_base", "medical_adapter", "teaching_base", "teaching_adapter"],
        "max_new_tokens": {"medical": 1200, "teaching": 1600}, "input_limit": 4096,
        "context_limit": 8192, "quantization": "NF4 double quant float16",
        "medical_evidence": "fixed source-reference passages, not actual retrieved context",
        "candidate_decision": "No candidate planned; prioritize predeclared base/adapter comparison, no tuning",
        "budgets": {"total": 800, "medical_final": 400, "teaching_final": 120, "development": 40,
                    "candidate_development": 20, "candidate_final": 200},
        "retry_policy": "none automatically; terminal model errors remain in denominator"})
    names = [p.name for p in DATA.iterdir() if p.suffix in {".json", ".jsonl"} and p.name != "manifest.json"]
    write(DATA / "manifest.json", {"revision": "medresident-benchmark-v1", "frozen_at": datetime.now(UTC).isoformat(),
        "questions": len(questions), "topics": len(TOPICS), "medical_development": 50, "medical_test": 200,
        "teaching_test": 60, "human_reviewed": False, "clinician_approved": False,
        "authoring_code_sha256": file_hash(ROOT / "local_model_testing/experiment/authoring.py"),
        "files": {name: file_hash(DATA / name) for name in sorted(names)}})
    RUN.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"frozen": True, "questions": len(questions), "medical_samples": len(samples),
                      "teaching_final_inputs": len(teaching_ref), "corpus_chunks": len(corpus)}))


if __name__ == "__main__":
    prepare()
