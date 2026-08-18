import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CURRICULUM_DIR = PROJECT_ROOT / "data" / "curriculum"
CURRICULUM_FILE = CURRICULUM_DIR / "curriculum_map.json"
SCHEMA_FILE = CURRICULUM_DIR / "curriculum_map.schema.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_schema(data: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)

    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: list(error.absolute_path),
    )

    messages = []

    for error in errors:
        location = ".".join(str(item) for item in error.absolute_path)
        location = location or "<root>"

        messages.append(
            f"Lỗi schema tại {location}: {error.message}"
        )

    return messages


def collect_courses(data: dict) -> list[dict]:
    courses = []

    for group in data.get("course_groups", []):
        for course in group.get("courses", []):
            courses.append(
                {
                    **course,
                    "curriculum_group_id": group.get("group_id"),
                }
            )

    return courses


def validate_business_rules(data: dict) -> list[str]:
    errors = []
    courses = collect_courses(data)

    course_codes = [
        course.get("course_code")
        for course in courses
    ]

    duplicate_codes = sorted(
        {
            code
            for code in course_codes
            if code and course_codes.count(code) > 1
        }
    )

    if duplicate_codes:
        errors.append(
            f"course_code bị trùng: {duplicate_codes}"
        )

    round_2_courses = [
        course for course in courses
        if course.get("round") == 2
    ]

    if len(round_2_courses) != 4:
        errors.append(
            f"Round 2 phải có 4 học phần, hiện có "
            f"{len(round_2_courses)}."
        )

    round_2_credits = sum(
        course.get("total_credits", 0)
        for course in round_2_courses
    )

    if round_2_credits != 24:
        errors.append(
            f"Round 2 phải có 24 tín chỉ, hiện có "
            f"{round_2_credits}."
        )

    round_3_courses = [
        course for course in courses
        if course.get("round") == 3
    ]

    if len(round_3_courses) != 8:
        errors.append(
            f"Round 3 phải có 8 học phần, hiện có "
            f"{len(round_3_courses)}."
        )

    invalid_round_3_credits = [
        course.get("course_code")
        for course in round_3_courses
        if course.get("total_credits") != 4
    ]

    if invalid_round_3_credits:
        errors.append(
            "Các học phần Round 3 không có đúng 4 tín chỉ: "
            f"{invalid_round_3_credits}"
        )

    specialty_block = (
        data.get("scope", {})
        .get("primary_specialty_block", {})
    )

    declared_total = specialty_block.get("total_credits")

    calculated_total = (
        round_2_credits
        + 4 * 4
    )

    if declared_total != 40:
        errors.append(
            f"Khối chuyên ngành phải khai báo 40 tín chỉ, "
            f"hiện là {declared_total}."
        )

    if calculated_total != 40:
        errors.append(
            f"Tổng tín chỉ tính theo Round 2 và quy tắc "
            f"chọn 4 học phần Round 3 là {calculated_total}, "
            "không phải 40."
        )

    if "B21CN1" not in course_codes:
        errors.append("Không tìm thấy học phần nền tảng B21CN1.")

    return errors


def main() -> None:
    try:
        curriculum = load_json(CURRICULUM_FILE)
        schema = load_json(SCHEMA_FILE)
    except (FileNotFoundError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}")
        sys.exit(1)

    schema_errors = validate_schema(curriculum, schema)
    rule_errors = validate_business_rules(curriculum)

    all_errors = schema_errors + rule_errors

    if all_errors:
        print("=== CURRICULUM VALIDATION FAILED ===")

        for index, error in enumerate(all_errors, start=1):
            print(f"{index}. {error}")

        sys.exit(1)

    courses = collect_courses(curriculum)

    print("=== CURRICULUM VALIDATION PASSED ===")
    print(f"Program: {curriculum['program']['program_name']}")
    print(f"Specialty: {curriculum['program']['specialty']}")
    print(f"Tổng số học phần: {len(courses)}")
    print("Round 1:", sum(c["round"] == 1 for c in courses))
    print("Round 2:", sum(c["round"] == 2 for c in courses))
    print("Round 3:", sum(c["round"] == 3 for c in courses))


if __name__ == "__main__":
    main()