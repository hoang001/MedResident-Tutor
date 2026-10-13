"""Pure deterministic post-processing; edits only priority and feedback text."""

import copy
import re
import unicodedata

CAUTION = "Medical Evaluation cho biết bằng chứng hiện có không đủ để kết luận về phần nằm ngoài các tiêu chí đã chấm."
RECURRING_REASON = "Đây là lỗi/thiếu sót đã lặp lại gần đây nên cần ưu tiên xử lý."
SIMILARITY_THRESHOLD = 0.85
AMBIGUITY_MARGIN = 0.10


def normalize(text):
    # Keep diacritics and negation tokens; accent stripping risks conflating facts.
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold()))


def match_point(text, points):
    """Unique normalized substring first, then token Jaccard >= .85.

    Require >=4 distinct tokens and a .10 runner-up margin for fuzzy matching.
    Negation tokens must agree for fuzzy matches. Ties are never resolved by order.
    """
    if not isinstance(text, str):
        return None
    normalized = normalize(text)
    if not normalized:
        return None
    points = list(dict.fromkeys(p for p in points if isinstance(p, str) and p.strip()))
    exact = [p for p in points if normalize(p) == normalized]
    if len(exact) == 1:
        return exact[0]
    # Only accept an entire current point embedded in a summary or focus.
    negations = {"không", "chưa", "chẳng", "not", "no", "without"}
    tokens = set(normalized.split())
    substrings = [p for p in points if len(set(normalize(p).split())) >= 4
                  and f" {normalize(p)} " in f" {normalized} "]
    if len(substrings) == 1:
        return substrings[0]
    if len(substrings) > 1:
        return None
    if len(tokens) < 4:
        return None
    ranked = []
    for point in points:
        other = set(normalize(point).split())
        if len(other) < 4 or (tokens & negations) != (other & negations):
            continue
        ranked.append((len(tokens & other) / len(tokens | other), point))
    ranked.sort(reverse=True)
    if not ranked or ranked[0][0] < SIMILARITY_THRESHOLD:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < AMBIGUITY_MARGIN:
        return None
    return ranked[0][1]


def append_once(text, sentence):
    if normalize(sentence) in normalize(text):
        return text
    return text + (" " if text else "") + sentence


def apply_teaching_guards(payload, prediction):
    """Return a copy; invalid editable field shapes are left untouched."""
    result = copy.deepcopy(prediction)
    if not isinstance(result, dict):
        return result
    med = payload["medical_evaluation"]
    feedback = result.get("feedback_text")
    if isinstance(feedback, str) and med.get("sufficient_evidence") is False:
        result["feedback_text"] = append_once(feedback, CAUTION)
    context = payload.get("learner_context", {})
    issues = med["incorrect_points"] + med["missing_points"]
    recurring = set()
    for entry in context.get("recurring_errors", []):
        if isinstance(entry, dict):
            matched = match_point(entry.get("error_summary"), issues)
            if matched is not None:
                recurring.add(matched)
    priorities = result.get("learning_priority")
    if isinstance(priorities, list):
        promoted, remaining = [], []
        for item in priorities:
            matched = match_point(item.get("focus"), issues) if isinstance(item, dict) else None
            if (matched in recurring and isinstance(item.get("reason"), str)
                    and item.get("priority") in {"high", "medium", "low"}):
                item["priority"] = "high"
                item["reason"] = append_once(item["reason"], RECURRING_REASON)
                promoted.append(item)
            else:
                remaining.append(item)
        result["learning_priority"] = promoted + remaining
    if isinstance(result.get("feedback_text"), str):
        for entry in context.get("recent_improvements", []):
            if not isinstance(entry, dict):
                continue
            point = match_point(entry.get("improvement_summary"), med["correct_points"])
            if point is not None:
                sentence = f"Bạn đã cải thiện ở nội dung: {point}"
                result["feedback_text"] = append_once(result["feedback_text"], sentence)
    return result
