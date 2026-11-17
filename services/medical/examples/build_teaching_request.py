"""Build a protocol probe using the actual Medical response, without changing it."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("medical_request", type=Path)
    parser.add_argument("medical_response", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    request = json.loads(args.medical_request.read_text(encoding="utf-8"))
    response = json.loads(args.medical_response.read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0.0",
        "question": request["question"],
        "student_answer": request["student_answer"],
        "medical_evaluation": response["medical_evaluation"],
        "learner_context": {
            "mastery": [],
            "recurring_errors": [],
            "recent_improvements": [],
            "recent_attempts_summary": None,
        },
        "metadata": {
            "specialty": None,
            "course_group": None,
            "course_id": None,
            "course_name": None,
            "specialty_level": None,
            "topic_id": None,
            "topic_name": None,
            "concept_ids": [],
        },
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
