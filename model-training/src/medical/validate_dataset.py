import json
from pathlib import Path


FORBIDDEN_QUESTIONS = {
    "Q_0012",
    "Q_0013",
    "Q_0014",
    "Q_0015",
    "Q_0016",
}


def find_repo_root() -> Path:
    current = Path(__file__).resolve()

    for directory in [current.parent, *current.parents]:
        if (
            (directory / ".git").exists()
            and (directory / "data").exists()
        ):
            return directory

    raise RuntimeError("Không tìm thấy repository root.")


ROOT = find_repo_root()

TRAINING_DIR = ROOT / "data" / "training"

SPLITS = {
    "train": TRAINING_DIR / "medical_train.jsonl",
    "validation": TRAINING_DIR / "medical_validation.jsonl",
    "test": TRAINING_DIR / "medical_test.jsonl",
}


def read_jsonl(path: Path):
    rows = []

    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path.name}: JSON lỗi ở dòng {line_number}: {exc}"
                )

    return rows


def get_gold(sample):
    """
    Hỗ trợ cả:
    {
        "gold_output": {...}
    }

    hoặc output nằm trực tiếp trong sample.
    """
    for key in (
        "gold_output",
        "medical_evaluation",
        "expected_output",
        "output",
        "assistant",
    ):
        if isinstance(sample.get(key), dict):
            return sample[key]

    required = {
        "correct_points",
        "incorrect_points",
        "missing_points",
        "rubric_scores",
        "total_score",
        "max_score",
        "sufficient_evidence",
        "evidence_refs",
    }

    if required.issubset(sample):
        return sample

    return None


def score_sum(rubric_scores):
    if isinstance(rubric_scores, dict):
        return sum(
            value
            for value in rubric_scores.values()
            if isinstance(value, (int, float))
        )

    if isinstance(rubric_scores, list):
        total = 0

        for item in rubric_scores:
            if isinstance(item, (int, float)):
                total += item

            elif isinstance(item, dict):
                score = (
                    item.get("score")
                    if "score" in item
                    else item.get("awarded_score")
                )

                if isinstance(score, (int, float)):
                    total += score

        return total

    return None


def extract_source_ids(sample):
    result = set()

    evidence = sample.get("evidence", [])

    if isinstance(evidence, dict):
        evidence = [evidence]

    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, str):
                result.add(item)

            elif isinstance(item, dict):
                for key in (
                    "source_unit_id",
                    "source_id",
                    "id",
                ):
                    value = item.get(key)

                    if isinstance(value, str):
                        result.add(value)
                        break

    return result


def validate_sample(sample, split_name):
    errors = []

    required_fields = [
        "sample_id",
        "question_id",
        "question",
        "student_answer",
        "evidence",
        "rubric",
    ]

    for field in required_fields:
        if field not in sample:
            errors.append(f"Thiếu field: {field}")

    question_id = sample.get("question_id")

    if question_id in FORBIDDEN_QUESTIONS:
        errors.append(
            f"Question bị cấm xuất hiện trong dataset: {question_id}"
        )

    gold = get_gold(sample)

    if gold is None:
        errors.append("Không tìm thấy gold medical output.")
        return errors

    required_gold = [
        "correct_points",
        "incorrect_points",
        "missing_points",
        "rubric_scores",
        "total_score",
        "max_score",
        "sufficient_evidence",
        "evidence_refs",
    ]

    for field in required_gold:
        if field not in gold:
            errors.append(f"Gold output thiếu field: {field}")

    if errors:
        return errors

    calculated = score_sum(gold["rubric_scores"])

    if calculated is not None:
        if calculated != gold["total_score"]:
            errors.append(
                f"total_score={gold['total_score']} "
                f"nhưng tổng rubric_scores={calculated}"
            )

    if gold["total_score"] > gold["max_score"]:
        errors.append(
            "total_score lớn hơn max_score."
        )

    if not isinstance(gold["sufficient_evidence"], bool):
        errors.append(
            "sufficient_evidence phải là boolean."
        )

    for field in (
        "correct_points",
        "incorrect_points",
        "missing_points",
        "evidence_refs",
    ):
        if not isinstance(gold[field], list):
            errors.append(
                f"{field} phải là list."
            )

    return errors


def main():
    datasets = {}
    all_sample_ids = set()

    print("=== MEDICAL DATASET VALIDATION ===\n")

    total_errors = 0

    for split_name, path in SPLITS.items():
        if not path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy: {path}"
            )

        rows = read_jsonl(path)
        datasets[split_name] = rows

        print(
            f"{split_name}: {len(rows)} samples"
        )

        for index, sample in enumerate(rows, start=1):
            sample_id = sample.get("sample_id")

            if sample_id in all_sample_ids:
                print(
                    f"[ERROR] Trùng sample_id: {sample_id}"
                )
                total_errors += 1

            all_sample_ids.add(sample_id)

            errors = validate_sample(
                sample,
                split_name,
            )

            for error in errors:
                print(
                    f"[ERROR] {split_name} "
                    f"{sample_id or index}: {error}"
                )
                total_errors += 1

    print("\n=== LEAKAGE CHECK ===")

    question_sets = {
        split: {
            row.get("question_id")
            for row in rows
        }
        for split, rows in datasets.items()
    }

    source_sets = {
        split: set().union(
            *[
                extract_source_ids(row)
                for row in rows
            ]
        )
        if rows
        else set()
        for split, rows in datasets.items()
    }

    pairs = [
        ("train", "validation"),
        ("train", "test"),
        ("validation", "test"),
    ]

    for left, right in pairs:
        question_overlap = (
            question_sets[left]
            & question_sets[right]
        )

        print(
            f"{left} ↔ {right} question overlap:",
            len(question_overlap),
        )

        if question_overlap:
            print(
                "  ",
                sorted(question_overlap),
            )
            total_errors += 1

        source_overlap = (
            source_sets[left]
            & source_sets[right]
        )

        print(
            f"{left} ↔ {right} source overlap:",
            len(source_overlap),
        )

        if source_overlap:
            print(
                "  ",
                sorted(source_overlap),
            )
            total_errors += 1

    print("\n=== SUMMARY ===")
    print(
        "Tổng samples:",
        sum(
            len(rows)
            for rows in datasets.values()
        ),
    )

    print(
        "Sample IDs duy nhất:",
        len(all_sample_ids),
    )

    if total_errors == 0:
        print(
            "\n✅ DATASET VALIDATION PASSED"
        )
    else:
        print(
            f"\n❌ DATASET VALIDATION FAILED "
            f"({total_errors} lỗi)"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()