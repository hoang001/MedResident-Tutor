"""Source roles/ancestry for the offline textbook scope, without model calls."""

from scripts.prepare_2021_book import marker, units_for


def page(text):
    return {"text": text, "html": ""}


def test_objectives_questions_and_cross_page_parent_context_are_preserved():
    pages = {
        8: page(
            "Bài 1\nĐIỀU TRỊ GÃY XƯƠNG\nTác giả A\nTác giả B\n"
            "MỤC TIÊU HỌC TẬP\n1. Phân tích được chẩn đoán.\n"
            "NỘI DUNG HỌC TẬP\n1. ĐIỀU TRỊ\nNếu tổn thương nhẹ thì bảo tồn.\n"
            "1.1. Chỉ định\nĐiều kiện đầu tiên.\n13"
        ),
        9: page(
            "Điều kiện tiếp theo và ngoại lệ.\nTÀI LIỆU THAM KHẢO\n"
            "1. Tác giả tài liệu.\nCÂU HỎI LƯỢNG GIÁ\n"
            "Câu 1. Nêu chỉ định?\nA. Đáp án lựa chọn một\nB. Đáp án lựa chọn hai\n14"
        ),
    }
    _, gap, units, excluded, kept = units_for(1, 8, 9, pages)
    assert not gap
    objectives = [u for u in units if u["role"] == "learning_objective"]
    questions = [u for u in units if u["role"] == "question"]
    assert len(objectives) == len(questions) == 1
    assert questions[0]["lines"][-2:] == [(9, 5), (9, 6)]
    continued = next(u for u in units if (9, 0) in u["lines"])
    assert (8, 10) in continued["lines"] and (8, 7) in continued["parents"]
    assert (9, 2) not in kept
    assert any(r["reason"] == "bibliography_not_medical_prose" for r in excluded)


def test_missing_opening_uses_toc_only_without_dropping_first_clinical_line():
    pages = {
        5: page("MỤC LỤC"),
        6: page("Bài 14. Viêm xương tủy\nTác giả"),
        181: page("Đoạn chuyên môn tiếp nối đang có.\n1.2. Cơ chế\nĐoạn tiếp theo."),
    }
    ctx, gap, units, _, kept = units_for(14, 181, 181, pages)
    assert gap and ctx == [(6, 0)]
    assert (181, 0) in kept
    assert not any(u["role"] == "learning_objective" for u in units)


def test_clinical_sentence_about_questions_is_not_an_assessment_header():
    assert marker("Câu hỏi đặt ra là có nên mổ hay không?") is None
    assert marker("CÂU HỎI LƯU QUANG GIÁ") == "question"
