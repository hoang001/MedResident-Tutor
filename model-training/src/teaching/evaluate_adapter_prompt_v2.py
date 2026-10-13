"""Evaluate Teaching adapter V1 with system instructions V2 on validation only.

The unchanged adapter runner owns loading, generation, metrics and reports.
Only in-memory system messages, summary heading and report destination differ.
"""

import builtins
import copy
import hashlib
import json
from types import FunctionType

if __package__:
    from . import evaluate_adapter as adapter
else:
    import evaluate_adapter as adapter

OUTPUT_FILE = adapter.baseline.ROOT / "model-training/outputs/teaching-qwen2.5-v1/validation_prompt_v2.json"
PROMPT_V2_INSTRUCTIONS = """

INSTRUCTION V2 — BẮT BUỘC ÁP DỤNG TRƯỚC KHI XUẤT JSON:
Medical Evaluation là nguồn sự thật chuyên môn duy nhất. Không tự chấm lại,
không thay đổi score, correctness hoặc thêm factual medical knowledge ngoài
Medical Evaluation. strengths chỉ ánh xạ correct_points; corrections chỉ ánh xạ
incorrect_points; missing_focus chỉ ánh xạ missing_points, giữ đủ các ý hiện tại.
learner_context chỉ ảnh hưởng cách dạy, ưu tiên, thứ tự và wording.
follow_up_question chỉ dựa trên incorrect_points, missing_points hoặc nội dung
được Medical Evaluation xác nhận; không suy diễn từ claim trong student_answer.

RULE A — RECURRING CURRENT ERRORS:
Đối chiếu error_summary trong learner_context.recurring_errors với từng current
incorrect_point và missing_point theo nội dung, không chỉ theo concept_id chung.
Nếu có nội dung khớp: learning_priority của chính point đó phải là high và đứng
trước current issues không có recurring signal. Chỉ được xếp issue khác trước
nếu Medical Evaluation cung cấp lý do rõ ràng; ghi rõ lý do ấy, không tự suy diễn.
reason của point recurring bắt buộc nói rõ: "Đây là lỗi/thiếu sót đã lặp lại gần
đây nên cần ưu tiên xử lý." feedback_text phải nhắc ngắn gọn chính lỗi/thiếu sót
lặp lại đó cần xử lý trước. Không thêm medical fact để giải thích lịch sử.

RULE B — SPECIFIC RECENT IMPROVEMENTS:
Đối chiếu improvement_summary trong learner_context.recent_improvements với
current correct_points. Nếu khớp, feedback_text bắt buộc ghi nhận cụ thể nội dung
correct_point đã cải thiện, ví dụ "Bạn đã cải thiện ở nội dung: <correct_point
khớp từ Medical Evaluation>." Không chỉ nói chung chung "đã có tiến bộ".
strengths vẫn chỉ map từ correct_points; không đổi correctness, không thêm ý đúng.

RULE C — INSUFFICIENT EVIDENCE:
Nếu medical_evaluation.sufficient_evidence=false, feedback_text bắt buộc chứa
câu: "Medical Evaluation cho biết bằng chứng hiện có không đủ để kết luận về
phần nằm ngoài các tiêu chí đã chấm." Không xác nhận hoặc bác bỏ thêm claim
ngoài Medical Evaluation, không thêm medical knowledge để bù phần thiếu.

CONTEXT GUARDS:
Nếu learner_context rỗng, không bịa personalization, không nhắc learner_context
hoặc lịch sử học. Nếu recurring_errors/recent_improvements không map được current
medical points, có thể bỏ qua; không ép context vào medical correctness, không
suy diễn chỉ vì concept_id giống nhau. mastery chỉ ảnh hưởng sư phạm khi relevant.

Trước khi xuất, kiểm tra RULE A/B/C khi áp dụng và giữ đúng Teaching schema v1
gồm strengths, corrections, missing_focus, learning_priority, feedback_text,
follow_up_question. Chỉ xuất JSON; không thêm field hoặc văn bản ngoài JSON.
"""


def load_validation_prompt_v2():
    # The baseline loader is the sole dataset reader; never open another split.
    rows = copy.deepcopy(adapter.load_validation())
    for row in rows:
        row["messages"][0]["content"] += PROMPT_V2_INSTRUCTIONS
    return rows


def print_v2(*args, **kwargs):
    args = tuple(
        value.replace("=== TEACHING ADAPTER V1 SUMMARY ===",
                      "=== TEACHING ADAPTER V1 + PROMPT V2 SUMMARY ===")
        if isinstance(value, str) else value for value in args
    )
    builtins.print(*args, **kwargs)


def make_runner():
    # Execute the exact adapter main code with an isolated globals dictionary.
    # No monkey-patching of the imported baseline/adapter modules or source edits.
    namespace = dict(adapter.main.__globals__)
    namespace.update(load_validation=load_validation_prompt_v2, OUTPUT_FILE=OUTPUT_FILE,
                     print=print_v2, __doc__=__doc__)
    return FunctionType(adapter.main.__code__, namespace, "run_prompt_v2",
                        adapter.main.__defaults__, adapter.main.__closure__)


def main():
    make_runner()()
    # Record instructions separately: dataset hash still identifies unchanged SFT.
    report = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    report["prompt_version"] = "v2"
    report["system_instruction_appendix"] = PROMPT_V2_INSTRUCTIONS
    report["system_instruction_appendix_sha256"] = hashlib.sha256(
        PROMPT_V2_INSTRUCTIONS.encode("utf-8")
    ).hexdigest()
    OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
