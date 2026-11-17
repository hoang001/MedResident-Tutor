"""Explicit decisions authored after reading each dossier/PDF, not an auto-review."""

import argparse
import re

from review_2006_remaining import WORK, load_chapter

from document_toolkit.common import read_json, write_json


def base(number, viewed):
    _, _, _, pages, *_ = load_chapter(number)
    return {
        "dossier_fingerprint": read_json(
            WORK / f"bai-{number:02d}/input-manifest.json"
        )["dossier_fingerprint"],
        "all_graph_records_read": True,
        "pdf_viewed": viewed,
        "pdf_text_compared": [],
        "nodes": {},
        "edges": {},
        "held": {},
        "ocr": {},
        "missing": [],
        "review_notes": "Đối chiếu nguồn sách 2006; giữ nguyên quan điểm và số liệu lịch sử. Chưa phải chuyên gia y khoa duyệt.",
    }, pages


def patch(spec, pages, key, *pairs):
    page, line = map(int, key.split("."))
    text = spec["ocr"].get(key, pages[page]["raw_text"].splitlines()[line])
    for old, new in pairs:
        assert old in text, (key, old)
        text = text.replace(old, new)
    spec["ocr"][key] = text


def viewed_replacements(spec, pages, page_numbers, pairs):
    """Only use after the listed pages have actually been viewed; literal edits."""
    for page in page_numbers:
        assert page in spec["pdf_viewed"]
        for line, before in enumerate(pages[page]["raw_text"].splitlines()):
            after = spec["ocr"].get(f"{page}.{line}", before)
            for old, new in pairs:
                pattern = (
                    (r"(?<!\w)" if old[0].isalnum() else "")
                    + re.escape(old)
                    + (r"(?!\w)" if old[-1].isalnum() else "")
                )
                after = re.sub(pattern, lambda _m, replacement=new: replacement, after)
            if after != before:
                spec["ocr"][f"{page}.{line}"] = after


def keep(name=None, ranges=None, **kwargs):
    return {
        **({"name": name} if name else {}),
        **({"ranges": ranges} if ranges else {}),
        **kwargs,
    }


def hold(reason):
    return {"hold": True, "reason": reason}


def merge(target, reason):
    return {"merge_into": target, "reason": reason}


def recover(
    name,
    ranges,
    reason="Phục hồi đúng đối tượng đã được LLM đề xuất; bổ sung content từ đoạn PDF đã đọc, giữ đầy đủ điều kiện.",
    **kwargs,
):
    return {"recover": True, "name": name, "ranges": ranges, "reason": reason, **kwargs}


def edge(left, right, relation, ranges, condition=None):
    return {
        "recover": True,
        "from": left,
        "to": right,
        "type": relation,
        "ranges": ranges,
        "condition": condition,
        "reason": "Hai đầu và quan hệ được nêu rõ trong đoạn nguồn; sửa chiều/loại nếu đề xuất cũ sai. Không suy ra chỉ từ đồng xuất hiện.",
    }


def lesson3():
    s, p = base(3, list(range(16, 27)))
    replacements = {
        "16.0": [("GẤY XƯƠNG HỔ", "GÃY XƯƠNG HỞ")],
        "16.11": [("ngón chân, đầu", "ngón chân, đùi")],
        "17.0": [("gây xương hồ", "gãy xương hở")],
        "17.3": [("gay xương hồ", "gãy xương hở")],
        "17.9": [("gây xương hồ", "gãy xương hở")],
        "17.11": [
            ("Gây xương hồ", "Gãy xương hở"),
            ("gây hồ", "gãy hở"),
            ("xương gây", "xương gãy"),
        ],
        "17.13": [("gây gây xương hồ", "gây gãy xương hở"), ("gây hồ", "gãy hở")],
        "17.17": [("hoá khí", "hoả khí")],
        "17.18": [
            ("Gây xương hồ", "Gãy xương hở"),
            ("hoá khí", "hoả khí"),
            ("gây xương hồ", "gãy xương hở"),
        ],
        "17.19": [
            ("Gây xương hồ", "Gãy xương hở"),
            ("gây hồ", "gãy hở"),
            ("Xương thường gây", "Xương thường gãy"),
        ],
        "18.1": [("Gãy hồ", "Gãy hở"), ("lời cầu", "lồi cầu")],
        "18.2": [("màu chày đậm", "mào chày đâm")],
        "18.3": [("GẤY XƯƠNG HỒ", "GÃY XƯƠNG HỞ")],
        "18.6": [("gãy hồ", "gãy hở"), ("đập nát", "dập nát")],
        "18.7": [("bong lót", "bong lóc"), ("lót da", "lột da"), ("بیت", "bít")],
        "18.8": [("đụng đập", "đụng dập")],
        "18.9": [("gãy xương hồ", "gãy xương hở")],
        "18.10": [("đụng đập", "đụng dập"), ("gãy hồ", "gãy hở")],
        "18.11": [("đập nát", "dập nát")],
        "18.12": [("gãy xương hồ", "gãy xương hở")],
        "18.13": [("gãy xương hồ", "gãy xương hở"), ("bụi đất", "bùn đất")],
        "18.18": [("gãy xương hồ", "gãy xương hở")],
        "19.0": [("đập nát", "dập nát")],
        "19.3": [("đập nát", "dập nát")],
        "19.5": [("huyết khí", "yếm khí")],
        "19.6": [("Liên", "Liền"), ("liên xương", "liền xương")],
        "19.7": [("Liên", "Liền"), ("liên vết", "liền vết")],
        "19.8": [("vết thương liên", "vết thương liền")],
        "19.9": [("Liên", "Liền")],
        "19.11": [("đập nát", "dập nát")],
        "19.17": [("GẤY XƯƠNG HỒ", "GÃY XƯƠNG HỞ")],
        "20.10": [("cắt đứt", "cắt cụt")],
        "20.11": [("Đập nát", "Dập nát")],
        "20.12": [("vật đa-cân", "vạt da-cân"), ("vật cơ", "vạt cơ")],
        "20.13": [("dưng dấp", "đụng dập")],
        "20.19": [("tuý", "tuỷ")],
        "21.0": [("ổ gây", "ổ gãy")],
        "21.1": [("chảy máu", "chảy mủ")],
        "21.4": [("gây xương", "gãy xương")],
        "21.5": [
            ("gây xương", "gãy xương"),
            ("gây hở", "gãy hở"),
            ("dạng nặng cần cơ", "đụng dập nặng cân cơ"),
            ("cục tử", "cụt chi"),
        ],
        "21.6": [("gây hở", "gãy hở"), ("cần cứ", "căn cứ")],
        "21.13": [("ổ gây", "ổ gãy")],
        "21.14": [("Hỏi sức", "Hồi sức"), ("hỏi sức", "hồi sức"), ("gây hở", "gãy hở")],
        "22.1": [("gây xương", "gãy xương")],
        "22.7": [("2 thi", "2 thì")],
        "22.8": [("Thi bắn", "Thì bẩn")],
        "22.10": [("cơ đập nát", "cân cơ dập nát")],
        "22.11": [("xương bắn", "xương bẩn")],
        "22.12": [("mẫn sinh lý", "mặn sinh lý")],
        "22.13": [("Thi sạch", "Thì sạch")],
        "22.14": [
            ("trực chi", "trục chi"),
            ("cần rạch", "cân rạch"),
            ("hơn đa", "hơn da"),
        ],
        "22.15": [("đập nát", "dập nát"), ("đầu là cơ", "đâu là cơ")],
        "23.1": [("càn, cơ", "cân, cơ")],
        "23.3": [("gây hờ", "gãy hở")],
        "23.4": [("gây hờ", "gãy hở"), ("tai nạn bắn", "tai nạn bẩn")],
        "23.5": [("liên xương", "liền xương")],
        "23.8": [("gây kín", "gãy kín"), ("gây hở", "gãy hở")],
        "23.10": [("gây xương", "gãy xương"), ("cứu khi khởi", "cứu chi khỏi")],
        "23.13": [("khởi", "khỏi"), ("Khung cố cấu", "Khung có cấu")],
        "23.14": [("gây hờ", "gãy hở"), ("gây xương", "gãy xương")],
        "23.15": [("chính được", "chỉnh được")],
        "24.0": [("kỹ đầu", "kỳ đầu")],
        "25.1": [("lối cầu", "lồi cầu")],
        "25.7": [("gãy hỗ", "gãy hở")],
        "25.10": [("để hồ", "để hở"), ("gãy xương hỗ", "gãy xương hở")],
        "25.11": [
            ("Cầm khâu da, cần", "Cấm khâu da, cân"),
            ("gãy xương hỗ", "gãy xương hở"),
        ],
        "25.15": [("gãy hỗ", "gãy hở")],
        "25.19": [("gãy hỗ", "gãy hở")],
        "25.20": [("tụy", "tuỷ")],
        "26.4": [("gãy góc", "gấp góc"), ("sửa trực", "sửa trục")],
        "26.9": [("dùng phương pháp", "đúng phương pháp")],
        "26.10": [("rách rộng", "rạch rộng"), ("xương vùng", "xương vững")],
    }
    for key, pairs in replacements.items():
        patch(s, p, key, *pairs)
    s["printed_marker_restorations"] = ["25.11", "23.10"]
    canon = {
        "root": "MC_485db981fe124da3a01227402f6e298c",
        "classification": "MC_bad6dfb5263c4aa18bde65efbebc79bc",
        "wound": "MC_098dc95d415249229012b55e235df3b0",
    }
    s["nodes"] = {
        "N0": keep(
            "Gãy xương hở",
            [[16, 3, 5], [16, 8, 12], [26, 7, 9]],
            canonical_id=canon["root"],
        ),
        "N3": merge(
            "N0",
            "Cùng Condition gãy xương hở, kết luận cùng chương nhắc lại định nghĩa/đặc điểm; dùng binding canonical đã xác nhận.",
        ),
        "N1": keep("Nguyên nhân gãy xương hở — Thời bình", [[17, 11, 16]]),
        "N12": keep("Nguyên nhân gãy xương hở — Thời chiến", [[17, 16, 19]]),
        "N2": merge(
            "N36",
            "Cùng phương pháp bột bất động trong chương; đoạn lịch sử được giữ trong content phương pháp.",
        ),
        "N4": hold(
            "Đây là cơ chế chấn thương, không phải ClinicalPrinciple. Phục hồi hệ phân loại cơ chế và categories có nguồn rõ thay vì ép type."
        ),
        "N8": hold(
            "Đây là cơ chế chấn thương, không phải ClinicalPrinciple. Không nối GUIDED_BY cho nguyên nhân."
        ),
        "N5": hold(
            "Chỉ có bullet lịch sử tiến bộ kháng sinh, chưa mô tả can thiệp; các chỉ định kháng sinh sau mổ được giữ ở N45."
        ),
        "N11": hold(
            "Chỉ có bullet lịch sử tiến bộ tạo hình, không phải mô tả một can thiệp cụ thể."
        ),
        "N6": merge(
            "N35",
            "Cùng cố định ngoài được giới thiệu lịch sử và trình bày chi tiết ở mục6.2.2; không gộp vào category khung.",
        ),
        "N7": hold(
            "Nguồn nói tránh nhiễm trùng; không chứng minh nhiễm trùng là finding hiện diện."
        ),
        "N10": keep(
            "Gãy xương kín kèm vết thương phần mềm cùng đoạn chi", [[16, 4, 5]]
        ),
        "N14": keep(
            "Nhiễm trùng vết thương trong gãy xương hở",
            [[18, 15, 19], [19, 0, 6], [25, 21, 23]],
        ),
        "N18": keep(
            "Hoại tử da khi bong lóc trong gãy xương hở", [[18, 5, 8]], type="Condition"
        ),
        "N20": keep("Bất động chi phòng chống sốc trong gãy xương hở", [[19, 10, 13]]),
        "N22": keep("Sốc chấn thương trong gãy xương hở", [[19, 10, 13], [25, 18, 19]]),
        "N23": keep(
            "Nhiễm trùng yếm khí trong gãy xương hở", [[19, 5, 6], [25, 22, 23]]
        ),
        "N24": keep(
            "Cắt lọc, rạch rộng, để hở trong gãy xương hở", [[19, 6, 10], [26, 10, 11]]
        ),
        "N25": keep(
            "Phân độ gãy xương hở theo Gustilo",
            [[20, 4, 14], [21, 4, 7]],
            canonical_id=canon["classification"],
        ),
        "N27": keep("Đo giao động động mạch trong gãy xương hở", [[21, 3, 4]]),
        "N28": keep("Thì bẩn khi xử lý vết thương gãy xương hở", [[22, 7, 13]]),
        "N29": keep(
            "Xử lý vết thương phần mềm", [[22, 7, 22]], canonical_id=canon["wound"]
        ),
        "N30": keep(
            "Cấp cứu ban đầu gãy xương hở", [[21, 11, 21], [22, 0, 1], [26, 9, 10]]
        ),
        "N31": keep(
            "Thì sạch khi xử lý vết thương gãy xương hở", [[22, 7, 8], [22, 13, 22]]
        ),
        "N32": keep(
            "Điều trị gãy xương hở tại phòng chuẩn bị và phòng mổ", [[22, 1, 7]]
        ),
        "N34": keep("Khung cố định ngoài một khối (phân loại KCDN)", [[23, 11, 15]]),
        "N35": keep("Cố định ngoài trong gãy xương hở", [[17, 8, 9], [23, 6, 11]]),
        "N36": keep("Bó bột trong gãy xương hở", [[17, 1, 2], [25, 4, 8]]),
        "N38": keep("Kéo liên tục trong gãy xương hở chi dưới", [[25, 0, 4]]),
        "N40": keep("Kết hợp xương bên trong trong gãy xương hở", [[23, 0, 6]]),
        "N41": keep(
            "Khung cố định ngoài có khớp nối (phân loại KCDN)",
            [[23, 11, 12], [23, 15, 16], [24, 0, 2]],
        ),
        "N42": keep("Để hở da trong gãy xương hở nặng độ3", [[25, 8, 12]]),
        "N44": hold(
            "Một danh sách nhiều biến chứng không phải một Finding đơn nhất; giữ nguyên toàn bộ đề xuất ngoài graph."
        ),
        "N48": merge(
            "N22",
            "Cùng sốc sau gãy xương hở; mụcbiến chứng nhắc lại cùng nguyên nhân mất máu/đau.",
        ),
        "N49": keep(
            "Cấm khâu da, cân khi gãy xương hở đến muộn",
            [[25, 8, 12]],
            type="ClinicalPrinciple",
            reason="Ảnh PDF in CẤM, không phải can thiệp cầm/khâu; khôi phục phủ định và đổi thành nguyên tắc.",
        ),
        "N51": keep("Phục hồi phần mềm trong gãy xương hở", [[25, 8, 12]]),
        "N52": merge(
            "N14",
            "Cùng nhiễm khuẩn vết thương gãy hở, mục biến chứng sớm tương ứng mục3.2.1; giữ riêng các đoạn nguồn.",
        ),
        "N53": keep("Tắc mạch do mỡ tuỷ xương trong gãy xương hở", [[25, 20, 21]]),
        "N54": merge(
            "N30", "Cùng cấp cứu ban đầu được nhắc ở kết luận và trình bày tại mục6.1."
        ),
        "N55": keep(ranges=[[26, 0, 4]]),
        "N56": keep("Ghép xương khi chậm liền hoặc khớp giả sau gãy hở", [[26, 2, 4]]),
        "N57": keep("Phá can, sửa trục chi sau gãy hở có can lệch", [[26, 4, 5]]),
        "N60": merge(
            "N24",
            "Kết luận nhắc lại cùng cắt lọc/rạch rộng/để hở của mục3.2.3; không tạo thêm một phương pháp.",
        ),
        "N61": keep(
            "Cấp cứu và phẫu thuật kịp thời, đúng phương pháp",
            [[26, 9, 10]],
            type="ClinicalPrinciple",
        ),
    }
    invalid = {
        0: "Nguồn yêu cầu xử lý như gãy hở, không nói gãy kín gây gãy hở.",
        2: "Cơ chế không phải nguyên tắc.",
        4: "Bullet tiến bộ lịch sử không phải một chỉ định.",
        5: "Cơ chế không phải nguyên tắc.",
        6: "Bullet tiến bộ kháng sinh lịch sử không chứng minh quan hệ điều trị.",
        7: "Nguồn nói tránh nhiễm trùng, không phải finding có mặt.",
        8: "Nhiễm trùng lan vào xương không có nghĩa gây gãy xương hở.",
        21: "Thì mổ là bước xử lý, không phải subtype của can thiệp tổng.",
        22: "Thì mổ là bước xử lý, không phải subtype của can thiệp tổng.",
        27: "Đặt dẫn lưu là bước, không phải loại của phục hồi phần mềm.",
    }
    for i, reason in invalid.items():
        s["edges"][f"E{i}"] = hold(reason)
    s["edges"].update(
        {
            "E1": keep(
                ranges=[[23, 6, 11]],
                condition="Đặc biệt gãy hở nặng độ3, đến muộn hoặc nhiễm khuẩn",
            ),
            "E3": keep(ranges=[[25, 4, 8]]),
            "E11": keep(ranges=[[18, 15, 19], [19, 0, 1]]),
            "E14": edge("N0", "N23", "MAY_CAUSE", [[19, 5, 6]]),
            "E17": keep(ranges=[[19, 10, 13]]),
            "E23": keep(
                ranges=[[23, 6, 11]],
                condition="Đặc biệt gãy hở nặng độ3, đến muộn hoặc nhiễm khuẩn",
            ),
            "E24": keep(ranges=[[25, 0, 4]], condition="Áp dụng cho chi dưới"),
            "E25": keep(ranges=[[25, 4, 8]]),
            "E26": keep(
                ranges=[[23, 2, 6]],
                condition="Độ1 hoặc độ2 đến sớm, thể trạng tốt và phẫu thuật viên có kinh nghiệm; giữ chống chỉ định độ3a tại Việt Nam theo bản in2006",
            ),
            "E28": edge(
                "N0", "N42", "MANAGED_BY", [[25, 8, 12]], "Gãy xương hở nặng độ3"
            ),
            "E31": edge(
                "N0", "N49", "GUIDED_BY", [[25, 8, 12]], "Gãy xương hở đến muộn"
            ),
            "E33": keep(ranges=[[25, 8, 12]]),
            "E36": edge("N0", "N61", "GUIDED_BY", [[26, 9, 10]]),
        }
    )
    for i, name in [
        (5, "Cẳng chân"),
        (6, "Cẳng tay"),
        (7, "Các ngón tay"),
        (8, "Ngón chân"),
        (9, "Đùi"),
    ]:
        s["held"][f"H{i}"] = recover(name, [[16, 11, 12]])
    for i, h in enumerate(range(5, 10)):
        s["held"][f"H{i}"] = edge("N0", f"H{h}", "LOCATED_IN", [[16, 11, 12]])
    s["held"]["H11"] = edge(
        "N0", "N18", "MAY_CAUSE", [[18, 5, 8]], "Bong lóc da diện rộng, mất mạch nuôi"
    )
    s["held"]["H12"] = edge("N18", "N15", "LOCATED_IN", [[18, 5, 8]])
    s["held"]["H25"] = recover(
        "Phân loại gãy hở theo cơ chế chấn thương", [[19, 17, 21]]
    )
    s["held"]["H26"] = recover("Gãy hở ngoài vào (phân loại cơ chế)", [[19, 18, 20]])
    s["held"]["H27"] = recover(
        "Gãy hở trong ra (phân loại cơ chế)", [[19, 18, 19], [19, 20, 21]]
    )
    s["held"]["H13"] = edge("H25", "H26", "HAS_CATEGORY", [[19, 18, 20]])
    s["held"]["H14"] = edge("H25", "H27", "HAS_CATEGORY", [[19, 18, 19], [19, 20, 21]])
    s["held"]["H15"] = edge("N22", "N20", "MANAGED_BY", [[19, 10, 13]])
    s["held"]["H16"] = edge(
        "N14",
        "N24",
        "MANAGED_BY",
        [[19, 6, 10]],
        "Xử lý vết thương theo nguyên tắc gãy xương hở để phòng nhiễm khuẩn",
    )
    s["held"]["H28"] = recover(
        "Phân loại gãy xương hở theo thời gian (Friedrich)", [[20, 0, 4]]
    )
    s["held"]["H29"] = merge(
        "N25",
        "Cùng hệ Gustilo của chính chương3 và đoạn20.7; dùng binding canonical của hệ này.",
    )
    s["held"]["H17"] = edge("N0", "H28", "CLASSIFIED_BY", [[20, 0, 4]])
    s["held"]["H18"] = edge("N0", "N25", "CLASSIFIED_BY", [[20, 4, 14]])
    categories = [
        ("1", "MC_f903181961b044e68e303375f476538e"),
        ("2", "MC_7148dc6b07054c43b48206a422d47be2"),
        ("3", "MC_9312bc84a5944df68498a5feba6f6551"),
        ("3a", "MC_1fcc25417c6c4b829f1a9f39ce1f7077"),
        ("3b", "MC_d3d42831dee943f79b3083e44ee4850b"),
        ("3c", "MC_72f1e6d2069148dc8a79dca0cd9cc8d1"),
    ]
    for i, (grade, identifier) in enumerate(categories, 30):
        s["held"][f"H{i}"] = recover(
            "Gãy xương hở — Phân độ Gustilo — Độ " + grade,
            [[20, 7, 8], [20, i - 22, i - 21]],
            canonical_id=identifier,
        )
    for i, h in enumerate([30, 31, 32], 19):
        s["held"][f"H{i}"] = edge("N25", f"H{h}", "HAS_CATEGORY", [[20, 7, 11]])
    for i, h in enumerate([33, 34, 35], 22):
        s["held"][f"H{i}"] = edge(f"H{h}", "H32", "IS_A", [[20, 10, 14]])
    for i, name in [
        (50, "Chấn thương sọ não phối hợp gãy xương lớn"),
        (51, "Chấn thương ngực phối hợp gãy xương lớn"),
        (52, "Chấn thương bụng phối hợp gãy xương lớn"),
    ]:
        s["held"][f"H{i}"] = recover(name, [[21, 7, 9]])
    s["held"]["H53"] = recover(
        "Chụp CT trong đánh giá tổn thương phối hợp", [[21, 7, 10]]
    )
    s["held"]["H54"] = recover(
        "Siêu âm trong đánh giá tổn thương phối hợp", [[21, 7, 10]]
    )
    s["held"]["H39"] = edge("N33", "H53", "EVALUATED_BY", [[21, 7, 10]])
    s["held"]["H40"] = edge("N33", "H54", "EVALUATED_BY", [[21, 7, 10]])
    for i in [55, 62, 75, 83]:
        s["held"][f"H{i}"] = merge(
            "N0",
            "Cùng root gãy xương hở ở tiêu đề chương, phục hồi vào ID canonical đang dùng; không tạo thêm node từ heading rỗng.",
        )
    s["held"]["H41"] = edge("N0", "N30", "MANAGED_BY", [[21, 11, 21], [22, 0, 1]])
    s["held"]["H42"] = edge("N0", "N32", "MANAGED_BY", [[22, 1, 7]])
    s["held"]["H56"] = recover(
        "Thuốc phòng uốn ván trong cấp cứu gãy hở", [[21, 15, 17]]
    )
    s["held"]["H58"] = recover(
        "Thuốc giảm đau trong cấp cứu gãy hở", [[21, 15, 16], [21, 18, 19]]
    )
    s["held"]["H59"] = recover("Morphin", [[21, 18, 19]])
    s["held"]["H60"] = recover("Fèldène", [[21, 18, 19]])
    s["held"]["H61"] = recover("Rửa vết thương tại phòng chuẩn bị mổ", [[22, 2, 6]])
    s["held"]["H43"] = edge("N30", "H56", "USES_DRUG", [[21, 15, 17]])
    s["held"]["H45"] = edge(
        "N30",
        "H58",
        "USES_DRUG",
        [[21, 18, 19]],
        "Nếu chưa loại trừ những thương tổn khác thì không được dùng",
    )
    s["held"]["H46"] = edge(
        "N30",
        "H59",
        "USES_DRUG",
        [[21, 18, 19]],
        "Nếu chưa loại trừ những thương tổn khác thì không được dùng",
    )
    s["held"]["H47"] = edge(
        "N30",
        "H60",
        "USES_DRUG",
        [[21, 18, 19]],
        "Nếu chưa loại trừ những thương tổn khác thì không được dùng",
    )
    s["held"]["H49"] = edge("N0", "N29", "MANAGED_BY", [[22, 7, 22]])
    s["held"]["H66"] = edge(
        "N0",
        "N46",
        "MANAGED_BY",
        [[25, 15, 16]],
        "Gãy hở nặng; nếu cần sau48–72giờ có thể cắt lọc lại",
    )
    for i, n, ranges in [
        (67, "N22", [[25, 18, 19]]),
        (68, "N37", [[25, 19, 20]]),
        (69, "N53", [[25, 20, 21]]),
        (70, "N14", [[25, 22, 23]]),
        (71, "N39", [[25, 23, 24]]),
        (79, "N59", [[26, 0, 2]]),
        (80, "N55", [[26, 0, 3]]),
        (81, "N62", [[26, 0, 1], [26, 4, 5]]),
        (82, "N58", [[26, 0, 1], [26, 5, 6]]),
    ]:
        s["held"][f"H{i}"] = edge("N0", n, "MAY_CAUSE", ranges)
    s["held"]["H76"] = recover(
        "Băng và bất động phòng chống sốc sau gãy hở", [[25, 18, 19]]
    )
    s["held"]["H77"] = recover(
        "Rạch rộng, không khâu kín da khi xử lý gãy hở", [[25, 22, 23]]
    )
    s["held"]["H78"] = recover("Để chi tư thế cao sau mổ gãy hở", [[25, 23, 24]])
    s["held"]["H72"] = edge("N22", "H76", "MANAGED_BY", [[25, 18, 19]])
    s["held"]["H73"] = edge("N14", "H77", "MANAGED_BY", [[25, 22, 23]])
    s["held"]["H74"] = edge("N39", "H78", "MANAGED_BY", [[25, 23, 24]])
    s["missing"] = [
        {
            "pdf_pages": [19],
            "kind": "source_printed_discrepancy",
            "reason": "Đoạn văn ghi cẳng chân500–1000ml, bảng in100–1000ml; cả hai đã xem PDF, không tự thống nhất số. Chỉ giữ đoạn văn trong node sốc; bảng bảo toàn ở audit.",
        },
        {
            "pdf_pages": [20],
            "kind": "model_omitted_categories",
            "reason": "Hệ phân loại thời gian đã được đề xuất nhưng còn thiếu các category đến sớm/đến muộn/nhiễm trùng; chưa tự sinh category không có đề xuất.",
        },
        {
            "pdf_pages": [16, 24],
            "kind": "caption_review",
            "reason": "Đã xem caption thực hình3.1–3.3; caption hỗ trợ vị trí cẳng chân và loại khung; mô tả ảnh tiếng Anh do OCR/AI sinh không dùng làm bằng chứng.",
        },
    ]
    return s


def lesson4():
    s, p = base(4, list(range(27, 34)))
    changes = {
        "27.0": [("GÂY XƯƠNG", "GÃY XƯƠNG")],
        "27.2": [("Gây xương", "Gãy xương")],
        "27.6": [("căng dẫn", "căng dãn"), ("chất thấm", "chất ngấm")],
        "27.7": [("căng dẫn", "căng dãn")],
        "27.9": [("KỸ THUẬT MỞ", "KỸ THUẬT MỔ")],
        "28.1": [("đầu nút", "đầu mút"), ("đệm nát", "dập nát")],
        "28.5": [
            ("đầu nút", "đầu mút"),
            ("bọc lộ", "bộc lộ"),
            ("nào lộ qua", "nào lòi qua"),
        ],
        "28.11": [("có chằng", "có chừng")],
        "28.12": [("KHÀU", "KHÂU")],
        "28.13": [("bác cấu", "bắc cầu"), ("trụ trực", "trụ trục")],
        "28.14": [("Bọc lọc", "Bộc lộ")],
        "29.0": [("bậc lộ", "bộc lộ"), ("ngấn xương", "ngắn xương")],
        "30.2": [("thái loại", "thải loại")],
        "30.9": [("GÂY XƯƠNG", "GÃY XƯƠNG")],
        "30.12": [("phần xạ", "phản xạ")],
        "30.18": [("dưới gối", "dưới đùi")],
        "31.7": [("liệt tùy", "liệt tuỷ")],
        "31.10": [("trực cột", "trục cột"), ("mồm khớp", "mỏm khớp")],
        "31.13": [("cơ đuôi", "cơ duỗi"), ("cơ ngựa", "cơ ngửa")],
        "31.16": [("rử cổ cò", "rủ cổ cò")],
        "31.17": [("đuôi", "duỗi"), ("cơ cổ thần kinh", "cơ có thần kinh")],
        "31.18": [("đuôi", "duỗi")],
        "31.20": [("đập nặng", "dập nặng")],
        "32.0": [("căng dẫn", "căng dãn"), ("độn gấp", "đụng giập")],
        "32.1": [("mở", "mổ"), ("máy chỉ định", "mấy chỉ định")],
        "32.6": [("thần kinh trợ", "thần kinh trụ")],
        "32.7": [
            ("xương chổi", "xương chồi"),
            ("Thấy thuốc", "Thầy thuốc"),
            ("lỗi cầu", "lồi cầu"),
            ("vẹo dẫn", "vẹo dần"),
            ("thần kinh trợ", "thần kinh trụ"),
            ("dẫn dẫn", "dần dần"),
            ("sẽ mở", "sẽ mổ"),
        ],
        "32.8": [("thần kinh trợ", "thần kinh trụ")],
        "33.1": [("chòm", "chỏm"), ("mạnh võ hông", "mảnh vỡ hõm")],
        "33.3": [("căng dẫn", "căng dãn")],
        "33.5": [("ngã gây xương", "ngã gãy xương")],
        "33.7": [("bị đỏ", "bị đổ"), ("khởi váp", "khỏi vấp"), ("vật tép", "vạt tép")],
        "33.8": [
            ("bó bột cứng chân", "bó bột cẳng chân"),
            ("Tại biến", "Tai biến"),
            ("cắt hồ bột", "cắt hở bột"),
            ("khởi", "khỏi"),
        ],
        "33.10": [("bị đỏ", "bị đổ")],
    }
    for key, pairs in changes.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": keep(ranges=[[28, 6, 10]]),
        "N4": keep("Đứt thần kinh", [[27, 9, 15]]),
        "N6": keep(ranges=[[28, 0, 6]]),
        "N10": hold(
            "Đoạn28.13 có chữ Seddon ở vị trí cắt bỏ tổ chức, bản in không rõ nghĩa. Giữ ngoài thủ thuật kỳ2 này, không đoán tổ chức cần cắt."
        ),
        "N12": hold(
            "Đề xuất chỉ dựa đoạn khâu kỳ2 nói ít khi khâu bó; đoạn in còn mơ hồ chữ Seddon, không coi là chỉ định dương tính."
        ),
        "N15": hold(
            "Đoạn khâu kỳ2 chứa phát biểu không rõ nghĩa ngay trên bản in. Khâu vỏ bao nguyên phát N6 được giữ độc lập từ mục3.1."
        ),
        "N16": keep(ranges=[[30, 0, 9]]),
        "N17": keep("Phân loại ghép thần kinh theo nguồn cho", [[30, 0, 3]]),
        "N18": keep("Ghép thần kinh tự thân (phân loại nguồn cho)", [[30, 0, 3]]),
        "N22": keep("Ghép thần kinh đồng loại (phân loại nguồn cho)", [[30, 0, 3]]),
        "N25": keep("Ghép thần kinh khác loại (phân loại nguồn cho)", [[30, 0, 3]]),
        "N21": keep(
            "Làm ngắn xương để bù khuyết thần kinh", [[28, 14, 15], [29, 0, 1]]
        ),
        "N24": keep("Thần kinh cẳng tay bì trong và ngoài", [[30, 6, 7]]),
        "N26": keep(ranges=[[28, 14, 15], [29, 0, 1]]),
        "N31": keep(ranges=[[30, 10, 19], [31, 7, 11]]),
        "N33": keep("Bảng điểm liệt vận động được sách gọi là Frankel", [[31, 0, 7]]),
        "N34": keep(ranges=[[31, 14, 20]]),
        "N38": keep("Liệt tuỷ sau gãy cột sống", [[30, 10, 19], [31, 0, 11]]),
        "N41": keep("Bước đi kiểu vạt tép", [[33, 4, 8]]),
        "N44": keep(
            "Bàn chân bị đổ do liệt hông khoeo ngoài", [[33, 7, 8], [33, 10, 11]]
        ),
        "N45": keep(
            "Cắt hở bột để giải phóng chèn ép thần kinh tại cổ xương mác", [[33, 8, 9]]
        ),
        "N47": keep(ranges=[[33, 4, 11]]),
        "N49": keep(
            "Liệt cao thần kinh quay sau gãy thân xương cánh tay",
            [[31, 11, 21], [32, 0, 5]],
        ),
    }
    for i, reason in {
        2: "Vỏ bó chứa trụ trục, không phải một loại trụ trục; schema chưa có PART_OF.",
        9: "Thủ thuật kỳ2 không phải subtype của khâu bao; hai đầu và đoạn in kỳ2 chưa rõ.",
        10: "Nguồn nói ít khi khâu bó trong kỳ2; không chứng minh IS_A.",
        24: "Nguồn nói lót mép bột để tránh tai biến, chưa chứng minh điều trị liệt đã xảy ra.",
        26: "24giờ đầu là giai đoạn choáng tuỷ; không suy thành quan hệ liệt tuỷ gây choáng tuỷ.",
    }.items():
        s["edges"][f"E{i}"] = hold(reason)
    s["edges"].update(
        {
            "E0": keep(ranges=[[27, 9, 15], [28, 0, 6]]),
            "E1": keep(
                ranges=[[28, 6, 10]],
                condition="Thần kinh ít bó; không dùng cho thần kinh giữa1/3trên cẳng tay; không khâu căng",
            ),
            "E12": edge("N31", "N29", "EVALUATED_BY", [[31, 7, 10]]),
            "E13": keep(
                ranges=[[33, 8, 9]], condition="Chèn ép do mép bột cẳng chân dưới gối"
            ),
            "E14": keep(ranges=[[31, 14, 20]]),
            "E16": keep(ranges=[[31, 0, 7]]),
            "E17": edge("N31", "N35", "EVALUATED_BY", [[31, 7, 11]]),
            "E21": keep(
                ranges=[[33, 10, 11]],
                condition="Bàn chân đổ do liệt hông khoeo ngoài thường không tự hồi phục",
            ),
            "E23": keep(
                ranges=[[31, 20, 21], [32, 0, 1]],
                condition="Phân biệt thần kinh dập nặng/đứt với căng dãn, đụng giập nhẹ còn cảm giác",
            ),
        }
    )
    s["held"] = {
        "H0": recover(
            "Nhận biết vùng cảm giác riêng biệt của thần kinh để thăm khám",
            [[27, 2, 4], [32, 6, 7]],
            kind="cognitive",
        ),
        "H1": recover(
            "Dự đoán, tiên lượng thương tổn thần kinh", [[27, 4, 5]], kind="cognitive"
        ),
        "H8": recover("Gãy xương có biến chứng thần kinh", [[27, 0, 5]]),
        "H16": merge(
            "H8", "Cùng root chương, một bản ghi chỉ heading; không tạo node thứ hai."
        ),
        "H6": merge(
            "N20", "Cùng kỹ thuật khâu nhóm bó trong danh sách27.13 và mục3.3 trang28."
        ),
        "H17": merge(
            "N19",
            "Cùng thần kinh giữa giải phẫu được nhắc ở đoạn chuyển chỗ và khâu nhóm bó; không phải bệnh lý hoặc cấp tổn thương mới.",
        ),
        "H18": merge(
            "N14", "Cùng thần kinh trụ giải phẫu trong hai đoạn của cùng chương."
        ),
        "H19": merge(
            "N37",
            "Cùng thần kinh quay giải phẫu; nội dung thần kinh sau gãy có nguồn riêng, không merge với Condition liệt.",
        ),
        "H23": recover(
            "Bảo tồn liệt cao thần kinh quay sau gãy xương cánh tay", [[32, 0, 5]]
        ),
        "H24": recover("Liệt thần kinh trụ sau thương tổn tay", [[32, 5, 8]]),
        "H2": edge("H0", "H8", "APPLIES_TO", [[27, 2, 4]]),
        "H3": edge("H1", "H8", "APPLIES_TO", [[27, 4, 5]]),
        "H4": edge("N4", "N20", "MANAGED_BY", [[27, 9, 15], [28, 10, 12]]),
        "H9": edge("N4", "N20", "MANAGED_BY", [[27, 9, 15], [28, 10, 12]]),
        "H20": edge("N49", "N37", "LOCATED_IN", [[31, 11, 14]]),
        "H21": edge(
            "N49",
            "H23",
            "MANAGED_BY",
            [[32, 0, 5]],
            "Chờ3tháng; mổ cấp cứu/sớm chỉ một số trường hợp gãy hở, gấp góc di lệch nhiều, kèm thương tổn mạch",
        ),
    }
    s["missing"] = [
        {
            "pdf_pages": [28],
            "kind": "ambiguous_printed_text",
            "reason": "Bản in mục4 ghi cắt hết Seddon, không rõ tổ chức được nói tới; giữ các đề xuất chỉ có nguồn này ngoài graph, không tự sửa bằng kiến thức ngoài.",
        },
        {
            "pdf_pages": [30, 31],
            "kind": "printed_scale_identity",
            "reason": "Giữ đúng bảng nguồn gọi là Frankel với điểm0–5, và mốc cảm giác T2/T6/T10/T12/L1. Không đổi thang hoặc mốc theo kiến thức ngoài.",
        },
        {
            "pdf_pages": [27],
            "kind": "name_only_technique",
            "reason": "Khâu hỗn hợp chỉ có tên trong danh sách, chưa có mô tả; đề xuất được giữ ngoài thay vì lấp nội dung.",
        },
    ]
    return s


def lesson5():
    s, p = base(5, [34, 35, 36])
    s["printed_marker_restorations"] = ["34.3"]
    changes = {
        "34.3": [
            ("Tuy y vẫn có nếu", "Tuy y văn có nêu"),
            ("nhân ngựa", "nhân ngã ngựa"),
        ],
        "34.5": [("võ xương", "vỡ xương")],
        "34.10": [("Dút", "Đứt")],
        "34.12": [("mất chỉ", "mất chi")],
        "34.13": [("Máy ngày", "Mấy ngày"), ("tắc dẫn", "tắc dần")],
        "34.14": [("có rách dọc", "có rạch dọc"), ("Máy ngày", "Mấy ngày")],
        "34.15": [("được mở", "được mổ"), ("Máy ngày", "Mấy ngày")],
        "34.18": [("Do đặc", "Đo đạc"), ("võ xương", "vỡ xương")],
        "35.4": [("dút tĩnh", "đứt tĩnh")],
        "35.5": [("có sức nặng", "có sốc nặng")],
        "35.9": [("thát động", "thắt động")],
        "35.10": [("MÁT MÁU", "MẤT MÁU"), ("GÂY XƯƠNG DÙI", "GÃY XƯƠNG ĐÙI")],
        "35.11": [
            ("xương dài", "xương đùi"),
            ("chẳng có phải vôi vàng", "chả có phải vội vàng"),
            ("do đặc", "đo đạc"),
            ("xuống cúng", "xuống cáng"),
        ],
        "35.13": [("GÂY", "GÃY"), ("CẮNG", "CẲNG")],
        "35.14": [
            ("báp chân càng", "bắp chân căng"),
            ("kém dẫn", "kém dần"),
            ("rạch chân", "rạch cân"),
            ("Cần sâu", "Cân sâu"),
            ("không dẫn nở", "không dãn nở"),
        ],
        "35.15": [
            ("Do áp lực", "Đo áp lực"),
            ("rạch chân", "rạch cân"),
            ("là luôn 1", "là luồn 1"),
        ],
        "35.16": [("GÂY", "GÃY"), ("LỐI", "LỒI")],
        "35.17": [("bị kệt", "bị kẹt")],
        "36.0": [
            ("Sau chấn bó", "Sau nắn bó"),
            ("cho vừng", "cho vững"),
            ("90° thì", "90° thôi"),
        ],
        "36.1": [("DƯỚI ĐƠN", "DƯỚI ĐÒN"), ("VỪNG", "VÙNG")],
        "36.2": [("Hiểm gặp", "Hiếm gặp")],
        "36.3": [("hiến trong", "hiển trong")],
    }
    for key, pairs in changes.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N1": keep("Rách bên (phân loại thương tổn động mạch)", [[34, 8, 12]]),
        "N3": keep("Đứt đôi (phân loại thương tổn động mạch)", [[34, 8, 12]]),
        "N2": keep("Hồi sức cấp cứu sốc nặng sau vỡ xương chậu", [[35, 5, 10]]),
        "N7": keep(
            "Thắt động mạch chậu trong hai bên khi sốc vỡ chậu sau hồi sức",
            [[35, 5, 10]],
        ),
        "N8": keep(
            "Rách bong nội mạc (phân loại thương tổn động mạch)",
            [[34, 8, 10], [34, 12, 17]],
        ),
        "N9": hold(
            "Nguồn chảy máu là danh sách cấu trúc giải phẫu, không phải một Finding. Giữ source ở ngoài, không ép type danh sách thành một node."
        ),
        "N10": hold(
            "Đoạn hồi sức11lít là bệnh án thất bại lịch sử, không phải chỉ định điều trị hiện tại của sách. Regimen nguồn được giữ ở N2."
        ),
        "N11": keep(ranges=[[34, 17, 19], [35, 5, 10]]),
        "N12": keep(
            "Thương tổn động mạch sau gãy trên lồi cầu ở trẻ em",
            [[35, 16, 18], [36, 0, 1]],
        ),
        "N14": keep(ranges=[[35, 13, 16]]),
        "N15": keep("Rạch cân cẳng chân khi chèn ép khoang", [[35, 13, 16]]),
        "N17": keep(ranges=[[35, 10, 13]]),
        "N19": keep("Gãy xương đùi", [[35, 10, 13]]),
        "N18": keep("Luồn ống nhựa tạm thời giữa hai đầu mạch máu", [[35, 15, 16]]),
        "N22": keep("Buộc mạch máu khi không có điều kiện khâu nối", [[35, 15, 16]]),
        "N24": keep(
            "Hội chứng chèn ép khoang sau gãy1/3trên cẳng chân", [[35, 13, 16]]
        ),
        "N25": keep(ranges=[[36, 1, 3]]),
        "N27": keep("Ghép mạch máu bằng tĩnh mạch hiển trong", [[36, 3, 4]]),
    }
    for i, reason in {
        2: "Case truyền11lít thất bại không phải chỉ định đang được tác giả nêu.",
        3: "Nguồn chảy máu không phải một Finding đơn nhất.",
        4: "Đồng xuất hiện chèn ép khoang và thương tổn mạch chưa chứng minh chiều nhân quả đề xuất.",
        13: "Cắt bỏ đoạn mạch là bước xử lý, không phải quan hệ IS_A của xử trí tổng.",
        14: "Ghép mạch là thành phần xử lý, không phải IS_A của xử trí tổng.",
    }.items():
        s["edges"][f"E{i}"] = hold(reason)
    s["edges"].update(
        {
            "E0": keep(
                ranges=[[35, 5, 10]],
                condition="Một số ít bệnh nhân vỡ chậu có sốc nặng",
            ),
            "E1": keep(
                ranges=[[35, 5, 10]],
                condition="Sau truyền máu700ml, dịch3lít nhanh2giờ mà huyết áp tối đa vẫn dưới70mmHg",
            ),
            "E5": keep(condition="Giải pháp tạm thời trước chuyển chuyên khoa"),
            "E8": keep(
                condition="Rất hiếm ca mạch quay không đập do động mạch đứt đôi"
            ),
            "E10": keep(
                ranges=[[35, 14, 16]],
                condition="Đau buốt khi kéo ruỗi thụ động; áp lực khoang trên30mmHg",
            ),
            "E11": keep(
                ranges=[[35, 16, 18], [36, 0, 1]],
                condition="Sau nắn bó; nếu sưng nề nhiều phải đặt90° thay vì120°",
            ),
            "E12": edge("N19", "N17", "MAY_CAUSE", [[35, 10, 13]]),
            "E15": keep(ranges=[[36, 1, 4]]),
        }
    )
    s["held"] = {
        "H13": recover("Thương tổn động mạch sau gãy xương", [[34, 8, 17]]),
        "H14": recover("Phân loại thương tổn động mạch sau gãy xương", [[34, 8, 14]]),
        "H3": edge("H13", "H14", "CLASSIFIED_BY", [[34, 8, 14]]),
        "H4": edge("H14", "N3", "HAS_CATEGORY", [[34, 8, 12]]),
        "H5": edge("H14", "N1", "HAS_CATEGORY", [[34, 8, 12]]),
        "H6": edge("H14", "N8", "HAS_CATEGORY", [[34, 8, 14]]),
        "H7": edge(
            "H13",
            "N0",
            "MAY_CAUSE",
            [[34, 12, 16]],
            "Rách bong nội mạc gây tắc dần, thiếu máu ngoại vi",
        ),
        "H8": edge(
            "H13", "N4", "EVALUATED_BY", [[34, 16, 17]], "Khi có nghi ngờ trên lâm sàng"
        ),
        "H9": edge(
            "H13", "N6", "EVALUATED_BY", [[34, 16, 17]], "Khi có nghi ngờ trên lâm sàng"
        ),
        "H11": merge(
            "N19",
            "Cùng gãy xương đùi trong danh sách và mục4, không gộp với Condition sốc.",
        ),
        "H15": edge("N19", "N17", "MAY_CAUSE", [[35, 10, 13]]),
        "H16": edge(
            "N14",
            "N22",
            "MANAGED_BY",
            [[35, 15, 16]],
            "Không có điều kiện khâu nối; nguồn cảnh báo tỷ lệ mất chân cao3/4trở lên",
        ),
    }
    s["missing"] = [
        {
            "pdf_pages": [34],
            "kind": "name_only_conditions",
            "reason": "Các tên gãy chậu và cẳng chân vùng khoeo chỉ trong bullet nguy cơ, chưa đủ content riêng để phục hồi node trống. Không coi mọi gãy các vùng này là có biến chứng mạch.",
        },
        {
            "pdf_pages": [35, 36],
            "kind": "historical_treatment_scope",
            "reason": "Giữ nguyên phác đồ hồi sức700ml/3lít/2giờ và góc khuỷu120°/90° theo sách2006, không cập nhật bằng y văn ngoài.",
        },
    ]
    return s


def lesson6():
    s, p = base(6, list(range(37, 46)))
    changes = {
        "37.4": [("chấn thương gây", "chấn thương gãy")],
        "37.6": [("đụng đập", "đụng dập"), ("xương gây", "xương gãy")],
        "37.8": [("rấn chấn, bong", "rắn cắn, bỏng")],
        "37.17": [("phù lấp", "vùi lấp")],
        "37.21": [("rấn chấn", "rắn cắn"), ("do bong", "do bỏng")],
        "38.8": [("gây xương", "gãy xương")],
        "38.9": [("Gây xương hỗ", "Gãy xương hở")],
        "38.10": [("gây xương hỗ", "gãy xương hở"), ("gây hỗ", "gãy hở")],
        "38.12": [("sưng dập", "đụng dập")],
        "39.6": [("dòng vi quản", "dòng vi quản")],
        "39.17": [("Mao mạch", "mao mạch")],
        "39.18": [("dái ra", "đái ra")],
        "39.20": [("đồ dạng", "dở dang"), ("toàn chuyển", "toan chuyển")],
        "40.1": [("cứng tay", "cẳng tay")],
        "40.3": [("CĂNG -", "CẲNG -")],
        "40.6": [("Cả cứng tay cứng cứng", "Cả cẳng tay căng cứng")],
        "40.12": [
            ("Cơ thể chấn thương", "Cơ chế chấn thương"),
            ("cứng tay", "cẳng tay"),
        ],
        "40.16": [
            ("vôi 3 chạc", "vòi 3 chạc"),
            ("huyết thanh mặt phẳng trường", "huyết thanh mặn đẳng trương"),
        ],
        "41.19": [("mổ càn", "mở cân")],
        "42.6": [("Đau chi", "Đầu chi"), ("hồng, ẩm", "hồng, ấm")],
        "42.15": [("căng tay mềm", "cẳng tay mềm")],
        "42.18": [("mồm khuỷu", "mỏm khuỷu"), ("trăm quay", "trâm quay")],
        "42.20": [("khởi", "khỏi")],
        "43.0": [("Đường mạch máu", "Đường rạch cân")],
        "43.2": [("đuôi cổ", "duỗi cổ")],
        "43.4": [("CẮNG CHÂN", "CẲNG CHÂN")],
        "43.9": [("bóp chân", "bắp chân")],
        "43.12": [("Cẳng cứng", "Căng cứng")],
        "43.14": [("cẳng dẫn cơ bóp", "căng dãn cơ bắp")],
        "43.17": [("rạch chân", "rạch cân")],
        "44.10": [("cơ bắp", "cơ dép"), ("chạy sau", "chày sau")],
        "45.2": [("chi gây", "chi gãy")],
        "45.9": [("nhiễm toàn", "nhiễm toan")],
    }
    for key, pairs in changes.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N7": merge(
            "N9",
            "Cùng hội chứng chung được định nghĩa ở37.2 và nhắc lại ở kết luận45; không gộp subtype cẳng tay/cẳng chân.",
        ),
        "N9": keep(ranges=[[37, 0, 3], [37, 10, 11], [45, 5, 10]]),
        "N14": keep(
            "Gãy xương kín hoặc hở độ1–2 có nguy cơ chèn ép khoang",
            [[37, 11, 14], [38, 7, 11]],
        ),
        "N16": keep("Hội chứng vùi lấp", [[37, 11, 18]]),
        "N20": keep("Rạch cân giải phóng chèn ép khoang", [[40, 2, 3], [45, 8, 9]]),
        "N21": keep("Đái ra myoglobin khi chèn ép khoang kéo dài", [[39, 18, 20]]),
        "N25": keep(
            "Cắt cụt chi khi chèn ép khoang nặng không xử trí kịp",
            [[40, 1, 3]],
            type="Intervention",
        ),
        "N27": hold(
            "LBF là biến trong công thức dòng máu, chưa phải một ClinicalPrinciple độc lập."
        ),
        "N28": keep("Cẳng tay căng cứng, tròn như ống", [[40, 3, 7]]),
        "N30": keep("Hội chứng chèn ép khoang cẳng–bàn tay cấp tính", [[40, 3, 11]]),
        "N31": keep("Vòng luẩn quẩn áp lực khoang và tưới máu hạ lưu", [[39, 7, 15]]),
        "N32": keep(
            "Tổn thương thần kinh do chèn ép khoang", [[39, 2, 7]], type="Condition"
        ),
        "N34": keep("Hội chứng Wolkmann cẳng tay", [[40, 1, 2], [43, 1, 4]]),
        "N40": keep("Rạch cân giải phóng khoang cẳng–bàn tay", [[42, 16, 23]]),
        "N42": keep("Doppler mạch trong phân biệt rối loạn dinh dưỡng", [[42, 4, 9]]),
        "N45": merge(
            "N34",
            "Cùng Wolkmann cẳng tay: di chứng tại chỗ và điều trị sớm/muộn được mô tả trong cùng phần4.",
        ),
        "N46": keep(
            "Rối loạn dinh dưỡng cần phân biệt với chèn ép khoang", [[42, 4, 9]]
        ),
        "N47": keep("Đo áp lực khoang bằng Whiteside", [[40, 14, 20]]),
        "N48": merge(
            "N40",
            "Cùng mở/rạch cân cẳng tay được chỉ định ở phần4.2 và mô tả tại4.4.2.",
        ),
        "N49": keep(
            "Theo dõi và điều trị bảo tồn chèn ép khoang cẳng tay", [[42, 10, 16]]
        ),
        "N50": keep(
            "Rạch da ngầm trong chèn ép khoang cẳng chân bán cấp", [[45, 0, 3]]
        ),
        "N51": keep(ranges=[[43, 4, 19]]),
        "N52": keep("Phẫu thuật giải phóng khoang cẳng chân", [[44, 7, 14]]),
        "N53": keep(
            "Rạch cân cẳng chân khi áp lực khoang cao", [[43, 17, 18], [44, 8, 11]]
        ),
        "N54": keep(
            "Chụp hình trong chèn ép khoang cẳng chân (Xquang, mạch máu, CT)",
            [[44, 0, 1]],
        ),
        "N58": keep("Căng cứng toàn bộ cẳng chân", [[43, 10, 13]]),
        "N59": keep(ranges=[[45, 0, 3]]),
        "N61": keep("Theo dõi chèn ép khoang cẳng chân", [[44, 2, 7]]),
        "N69": merge(
            "N20",
            "Cùng rạch cân chung được nhắc lại ở kết luận; các kỹ thuật theo vị trí vẫn tách riêng.",
        ),
    }
    s["edges"] = {
        "E8": hold(
            "Dòng máu là biến số của công thức, không phải subtype của nguyên tắc áp lực."
        ),
        "E10": hold(
            "Đoạn mô tả cơ chế vòng luẩn quẩn, chưa phải quan hệ GUIDED_BY điều trị."
        ),
        "E5": keep(type="MAY_CAUSE"),
        "E6": keep(type="MANAGED_BY"),
        "E15": edge("N46", "N42", "EVALUATED_BY", [[42, 4, 9]]),
        "E18": edge("N30", "N34", "MAY_CAUSE", [[40, 1, 2], [43, 1, 4]]),
        "E20": keep(
            condition="Sau6giờ không tiến triển, Pk<30mmHg, cẳng tay mềm và ngón cử động bình thường"
        ),
        "E22": keep(ranges=[[41, 23, 25]]),
        "E24": keep(ranges=[[40, 14, 20]]),
        "E29": keep(**{"from": "N51"}),
        "E32": keep(**{"from": "N51"}),
    }
    for i in [11, 12, 13, 16, 17, 19, 20, 21, 22, 23, 24]:
        s["edges"].setdefault(f"E{i}", {})["from"] = "N30"
    for h, n, ranges in [
        (5, 14, [[37, 11, 14], [38, 7, 11]]),
        (6, 11, [[37, 11, 15]]),
        (7, 6, [[37, 11, 16]]),
        (8, 12, [[37, 11, 17]]),
        (9, 16, [[37, 11, 18]]),
        (10, 18, [[37, 18, 20]]),
    ]:
        s["held"][f"H{h}"] = edge(f"N{n}", "N9", "MAY_CAUSE", ranges)
    for h, name in enumerate(
        [
            "Vai",
            "Cánh tay",
            "Mông",
            "Đùi",
            "Khoang sau bắp chân",
            "Khoang trước cẳng tay",
        ],
        23,
    ):
        s["held"][f"H{h}"] = recover(name, [[38, 0, 2]])
    for h, anatomy in enumerate(range(23, 29), 11):
        s["held"][f"H{h}"] = edge("N9", f"H{anatomy}", "LOCATED_IN", [[38, 0, 2]])
    s["held"].update(
        {
            "H21": edge(
                "N9",
                "N3",
                "HAS_FINDING",
                [[38, 11, 14]],
                "Giai đoạn muộn, thiếu máu nuôi",
            ),
            "H22": edge(
                "N9",
                "N2",
                "HAS_FINDING",
                [[39, 2, 4]],
                "Thần kinh bị chèn ép hoàn toàn về sau",
            ),
            "H29": edge("N32", "N19", "HAS_FINDING", [[39, 5, 7]]),
            "H30": edge("N9", "N21", "HAS_FINDING", [[39, 18, 19]], "Chèn ép quá4giờ"),
            "H31": edge("N9", "N24", "HAS_FINDING", [[39, 15, 18]]),
            "H33": edge("N51", "N9", "IS_A", [[43, 4, 8]]),
            "H36": merge(
                "N9", "Cùng root hội chứng từ tiêu đề, không tạo node tên rỗng."
            ),
            "H37": recover("Hội chứng chèn ép khoang cẳng chân bán cấp", [[45, 0, 3]]),
            "H34": edge("H37", "N50", "MANAGED_BY", [[45, 0, 3]]),
            "H35": edge("H37", "N59", "MANAGED_BY", [[45, 0, 3]]),
        }
    )
    s["missing"] = [
        {
            "pdf_pages": [41],
            "kind": "flowchart_structural_review",
            "reason": "Đã xem toàn bộ sơ đồ6.6: đường triệu chứng rõ và Pk>30 đến mở cân; nhánh<30 phải theo dõi rồi đánh giá lại. Không nhập đoạn Mermaid OCR bị rời thành thuật toán mới.",
        },
        {
            "pdf_pages": [38, 43, 45],
            "kind": "printed_caption_knowledge",
            "reason": "Caption/nhãn4khoang và đườngrạch đã xem PDF. Category cấp/báncấp/mạn có đề xuất nhưng thiếu Classification tương ứng; không nối HAS_CATEGORY trực tiếp từ Condition.",
        },
    ]
    return s


def lesson7():
    s, p = base(7, [46, 47, 48, 49])
    viewed_replacements(
        s,
        p,
        [46, 47, 48],
        [
            ("CẮT CỤC", "CẮT CỤT"),
            ("cắt cục", "cắt cụt"),
            ("Cục ở", "Cụt ở"),
            ("cục ở", "cụt ở"),
            ("hông", "hỏng"),
            ("gãy hỗ", "gãy hở"),
            ("để hỗ", "để hở"),
            ("mềm cục", "mỏm cụt"),
            ("cục sần", "cụt sẵn"),
            ("Thấy thuốc", "Thầy thuốc"),
            ("thấy thuốc", "thầy thuốc"),
            ("Cự ", "Cụt "),
            ("cự ", "cụt "),
            ("môm", "mỏm"),
            ("mỏng cụt", "mỏm cụt"),
            ("lấp vào", "lắp vào"),
            ("lấp chân", "lắp chân"),
            ("ngấn", "ngắn"),
            ("gân ruồi", "gân ruỗi"),
            ("Găm bỏ", "Gặm bỏ"),
        ],
    )
    for key, pairs in {
        "47.8": [("găm xương", "gặm xương")],
        "48.9": [("tự cốt", "tụ cốt")],
        "48.18": [("nên của", "nên cưa"), ("sọ da", "sẹo da")],
        "48.19": [("vào dù", "vào đùi"), ("cơ dù", "cơ đùi")],
        "48.21": [("cụt dù", "cụt đùi")],
        "48.22": [
            ("lối cầu", "lồi cầu"),
            ("xương dù", "xương đùi"),
            ("tập tễn", "tập tễnh"),
        ],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": keep("Để hở hoàn toàn đầu mỏm cụt nhiễm trùng", [[46, 12, 14]]),
        "N1": keep("Hỏng thần kinh và mạch máu của tay", [[46, 6, 8]]),
        "N2": keep(ranges=[[46, 6, 9]]),
        "N3": keep(ranges=[[46, 0, 14]]),
        "N5": keep("Đóng kín mỏm cụt và dẫn lưu khi không nhiễm trùng", [[46, 12, 14]]),
        "N6": keep("Chi hỏng nhưng không bị nhiễm trùng", [[46, 13, 14]]),
        "N8": keep("Xương chi dưới bị hỏng nặng", [[46, 6, 9]]),
        "N11": keep(
            "Đặt garô trong sơ cứu chi dập nát không cứu được",
            [[46, 14, 19], [47, 0, 1]],
        ),
        "N12": hold(
            "Toàn bộ content là mô tả hình bằng tiếng Anh do OCR/AI sinh, gọi sai cẳng tay. Caption thật PDF49 là cắt cụt1/3giữa cẳng chân; không dùng alt text làm nguồn."
        ),
        "N13": keep(ranges=[[48, 12, 15]]),
        "N14": keep(ranges=[[48, 17, 21]]),
        "N15": keep("Dập nát chi nặng không còn cứu vãn hoặc cụt sẵn", [[46, 14, 18]]),
        "N16": keep("Cắt cụt đùi", [[48, 21, 23]]),
        "N20": keep("Xử trí mỏm cụt chi trên", [[47, 2, 9], [47, 10, 23], [48, 0, 5]]),
        "N22": hold(
            "Nguồn mô tả thiết bị bàn tay giả và tiến bộ chế tạo, chưa phải can thiệp hoặc Skill; schema không có Device, không tự ép type."
        ),
        "N23": hold(
            "Nguồn chỉ nêu chân giả thử nghiệm ở Mỹ; chưa có mô tả can thiệp. Giữ ngoài theo schema hiện tại."
        ),
    }
    s["edges"] = {
        "E2": keep(
            condition="Chi hỏng không nhiễm trùng; nguồn lưu ý tai nạn để hở an toàn hơn"
        ),
        "E3": keep(
            ranges=[[46, 14, 19], [47, 0, 1]],
            condition="Chi dập nát không cứu được hoặc đã cụt sẵn; khác garô trong gãy hở còn khả năng cứu chi",
        ),
        "E5": keep(
            ranges=[[46, 14, 18], [46, 19, 20]],
            condition="Gãy hở nặng/rộng được băng ép; không coi mọi ca đều phải đặt garô",
        ),
    }
    s["held"] = {
        "H5": edge(
            "N1",
            "N2",
            "MANAGED_BY",
            [[46, 6, 9]],
            "Tai nạn làm hỏng thần kinh, mạch máu tay",
        ),
        "H6": edge(
            "N8", "N2", "MANAGED_BY", [[46, 6, 9]], "Tai nạn chi dưới, xương hỏng nặng"
        ),
        "H7": edge("N7", "N3", "MANAGED_BY", [[46, 12, 13]]),
        "H30": recover("Cắt cụt chi dưới", [[48, 5, 24]]),
    }
    for h, n, ranges in [
        (15, 19, [[48, 5, 10]]),
        (16, 21, [[48, 5, 6], [48, 10, 12]]),
        (17, 13, [[48, 5, 6], [48, 12, 15]]),
        (18, 10, [[48, 5, 6], [48, 15, 17]]),
        (19, 14, [[48, 5, 6], [48, 17, 21]]),
        (20, 16, [[48, 5, 6], [48, 21, 23]]),
    ]:
        s["held"][f"H{h}"] = edge(f"N{n}", "H30", "IS_A", ranges)
    s["missing"] = [
        {
            "pdf_pages": [49],
            "kind": "generated_alt_text_excluded",
            "reason": "Bỏ đề xuất và Anatomy tiếng Anh lấy từ alt text AI. Hình7.1 thật là cẳng chân, có nhãn số8.8–12.5cm,0.9–1.3cm,12.5–15cm; chỉ giữ audit, chưa biến các nhãn hình thành hướng dẫn mới.",
        },
        {
            "pdf_pages": [47],
            "kind": "printed_text_ambiguity",
            "reason": "Câu khâu da đầu ngón ghi5–6 đầu ngón tay; bản in không rõ thành phần bị thiếu. Giữ đoạn trong nguồn audit, cần người dùng xem; không tự thêm đơn vị/lỗ.",
        },
    ]
    return s


def lesson8():
    s, p = base(8, list(range(50, 59)))
    viewed_replacements(
        s,
        p,
        list(range(50, 59)),
        [
            ("cut", "cụt"),
            ("ngôn", "ngón"),
            ("đứt rồi", "đứt rời"),
            ("tỉnh mạch", "tĩnh mạch"),
            ("Tỉnh mạch", "Tĩnh mạch"),
            ("giằng giặt", "giằng giật"),
            ("đập nát", "dập nát"),
            ("bóc lộ", "bộc lộ"),
            ("Bóc lộ", "Bộc lộ"),
            ("ngấn", "ngắn"),
            ("gân đuôi", "gân duỗi"),
            ("gân đuổi", "gân duỗi"),
            ("gân ruồi", "gân ruỗi"),
            ("Nối chung", "Nói chung"),
            ("nối chung", "nói chung"),
        ],
    )
    viewed_replacements(
        s,
        p,
        [51],
        [("gãy giết", "giằng giật"), ("giết nát", "giật nát"), ("gãy", "ngón")],
    )
    changes = {
        "50.0": [("NÓI LẠI", "NỐI LẠI")],
        "50.4": [
            ("nơi cho tưới", "nối cho tưới"),
            ("mở ngắn", "mổ ngắn"),
            ("tính mạch", "tĩnh mạch"),
        ],
        "50.5": [("kẹp mở", "kíp mổ")],
        "50.7": [("khó mở", "khó mổ")],
        "50.14": [("Khủy", "Khuỷu"), ("khủy", "khuỷu")],
        "50.15": [("chung hông", "chung nông")],
        "50.16": [("mồm cụt", "mỏm cụt")],
        "51.4": [("ở đầu cũng", "ở đâu cũng")],
        "51.10": [("Phần chi định", "Phần chỉ định")],
        "51.13": [
            ("chơi vi cảm. dương cảm", "chơi vĩ cầm, dương cầm"),
            ("ngón chỗ", "ngón chỏ"),
        ],
        "51.15": [("mà chò", "mà chờ")],
        "51.17": [("kịp mổ", "kíp mổ")],
        "52.0": [("mỗi mất", "mỏi mắt")],
        "52.1": [("và độ khâu", "và đồ khâu")],
        "52.6": [("mỗi một", "mỏi mệt")],
        "53.0": [("XỬ TRÍ MỞ", "XỬ TRÍ MỔ"), ("nhóm phẫu nối", "nhóm khâu nối")],
        "53.4": [("vật da", "vạt da")],
        "53.5": [("để dàng", "dễ dàng")],
        "53.8": [("thông dái", "thông đái")],
        "53.12": [("vật da", "vạt da")],
        "53.13": [("MỞ NỐI", "MỔ NỐI")],
        "54.10": [("có giống phun", "có dòng phun")],
        "54.12": [("NGẤN", "NGẮN")],
        "54.19": [("cho khối xoay", "cho khỏi xoay")],
        "54.22": [("bờ mũ vít", "bỏ mũ vít")],
        "55.8": [("DUÔI", "DUỖI")],
        "55.13": [("rồi mở", "rồi mổ")],
        "55.14": [("khi mở thì đầu", "khi mổ thì đầu")],
        "55.17": [("Xong luôn", "Xong luồn")],
        "55.19": [("đuổi hết", "duỗi hết")],
        "56.0": [("Dút nhiều", "Đứt nhiều")],
        "56.1": [("khi mở thì", "khi mổ thì")],
        "57.2": [
            ("vì da số", "vì đa số"),
            ("cánh tay bì", "cẳng tay bì"),
            ("Tìm mồi trên lỗi", "Tìm mỏm trên lồi"),
            ("mồi trên rờng", "mỏm trên ròng"),
            ("bẻ rộng", "bề rộng"),
        ],
        "57.6": [("vật da", "vạt da"), ("rạch cần", "rạch cân")],
        "57.7": [("gần gấp", "gân gấp")],
        "57.9": [("khuyến đặt nghỉ", "khuỷu đặt nghỉ")],
        "57.17": [("thay bằng ngay", "thay băng ngay")],
        "58.1": [("thể luôn", "thể luồn"), ("thân kinh", "thần kinh")],
        "58.3": [("Luôn ngay", "Luồn ngay"), ("phần cắt", "phần cụt")],
    }
    for key, pairs in changes.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": keep(
            "Khuỷu và trên khuỷu sắc gọn, dập nát ít (nhóm nối tốt)",
            [[50, 8, 9], [50, 14, 15], [51, 3, 4]],
        ),
        "N1": keep("Cụt nhiều ngón (nhóm nối tốt)", [[50, 8, 11], [50, 16, 17]]),
        "N2": keep("Chi bị đứt rời", [[50, 3, 6], [52, 18, 19], [53, 0, 1]]),
        "N3": keep(
            "Chi thể trẻ em (nhóm nối lại)", [[50, 8, 9], [50, 12, 13], [51, 4, 5]]
        ),
        "N4": keep(ranges=[[50, 0, 3], [50, 6, 17], [53, 14, 15], [58, 7, 9]]),
        "N5": keep(ranges=[[50, 6, 17]]),
        "N6": merge(
            "N2",
            "Cùng Condition đứt rời hoàn toàn; nguồn định nghĩa phân biệt với cụt không hoàn toàn.",
        ),
        "N10": merge(
            "N2", "Cùng đối tượng đứt rời, bổ sung giới hạn giữ lạnh trong cùng chương."
        ),
        "N17": merge("N2", "Cùng đối tượng tới cấp cứu được nhắc trong mở kỳ đầu."),
        "N7": keep("Cụt có xơ hoá động mạch (nhóm khó nối)", [[51, 4, 12]]),
        "N8": keep(ranges=[[51, 4, 12]]),
        "N9": keep(ranges=[[50, 3, 6]]),
        "N11": keep(
            "Cổ tay, cẳng tay (nhóm nối tốt)", [[50, 8, 9], [50, 13, 14], [51, 3, 4]]
        ),
        "N12": keep("Thăm khám và phẫu tích bằng kính phóng đại", [[51, 16, 18]]),
        "N13": keep(ranges=[[51, 12, 13], [52, 10, 19]]),
        "N14": hold(
            "Danh sách dụng cụ không phải một can thiệp; không đổi Device thành Intervention để nhập."
        ),
        "N18": hold(
            "Kim và chỉ khâu là dụng cụ/vật liệu, không phải Drug. Giữ bảng kim/chỉ trong audit để xem."
        ),
        "N19": keep(ranges=[[53, 9, 11]]),
        "N21": keep(
            "Bupivacain (Marcaine)",
            content_groups=[[[53, 9, 11]], [[58, 0, 2]]],
            aliases=["Bupivacaine", "Marcaine"],
        ),
        "N23": keep("Xử lý phần chi còn lại trong nối chi", [[53, 7, 13]]),
        "N24": keep("Bóc tách tĩnh mạch để nối chi", [[53, 11, 13]]),
        "N25": keep(
            "Quan sát vi phẫu bằng kính hiển vi phẫu thuật", [[51, 16, 18], [52, 0, 1]]
        ),
        "N26": keep("Xử trí mổ kỳ đầu nối chi đứt rời", [[53, 0, 13]]),
        "N27": hold(
            "Dụng cụ vi phẫu là công cụ, chưa phải can thiệp hoặc Skill có căn cứ; không thêm taxonomy Device."
        ),
        "N28": keep(ranges=[[55, 8, 11]]),
        "N29": keep(ranges=[[54, 0, 3], [54, 10, 11]]),
        "N30": keep("Làm ngắn xương và cố định trong nối chi", [[54, 12, 17]]),
        "N31": keep(ranges=[[55, 8, 11]]),
        "N33": keep(
            "Kết hợp xương bằng đinh Kirschner chéo khi cần làm khớp",
            [[54, 17, 24], [55, 6, 8]],
        ),
        "N34": keep(
            "Khâu gân duỗi theo Kessler hay Tajima", [[55, 8, 11]], type="Intervention"
        ),
        "N35": merge(
            "N4",
            "Tên đối tượng là nối lại chi, nguồn mô tả kỹ thuật mổ; đó là Intervention N4, không phải Condition. Remap cạnh theo đúng bệnh cảnh gốc.",
        ),
        "N36": keep(
            "Quy trình mổ nối ngón tay và bàn tay", [[53, 13, 15], [54, 0, 12]]
        ),
        "N37": hold("Sợi polyester4-0 là chỉ khâu, không phải Drug."),
        "N38": merge(
            "N30",
            "Cùng làm ngắn và cố định xương ở thứ tự54.3 và phần7 tại54.12–17; sửa đoạn nguồn trích lệch của N30.",
        ),
        "N39": keep(
            "Kết hợp xương bằng nẹp vít khi nối chi lớn", [[54, 17, 24], [55, 7, 8]]
        ),
        "N40": keep(ranges=[[54, 17, 24], [55, 0, 8]]),
        "N41": keep(ranges=[[55, 8, 11]]),
        "N42": keep(content_groups=[[[57, 10, 11], [57, 14, 17]]]),
        "N45": keep(ranges=[[55, 15, 20]]),
        "N46": keep(ranges=[[57, 0, 5]]),
        "N47": keep(content_groups=[[[57, 10, 11], [57, 13, 14], [57, 15, 16]]]),
        "N49": keep(content_groups=[[[57, 10, 11], [57, 12, 13], [57, 15, 16]]]),
        "N51": keep(ranges=[[56, 2, 19]]),
        "N53": keep(ranges=[[58, 2, 7]]),
        "N54": keep(ranges=[[55, 11, 20], [56, 0, 2]]),
        "N55": keep(ranges=[[55, 11, 15], [56, 0, 2]]),
        "N56": keep(
            content_groups=[
                [[56, 17, 18]],
                [[57, 10, 11], [57, 17, 18]],
                [[58, 0, 2]],
                [[58, 2, 7]],
            ]
        ),
        "N59": merge(
            "N21",
            "Cùng thuốc Bupivacain/Bupivacaine trong chính chương, Marcaine được sách ghi trực tiếp. Giữ riêng block gây tê và truyền cạnh thần kinh sau mổ; không trộn các phác đồ.",
        ),
    }
    for i, reason in {
        2: "Định nghĩa phân biệt hoàn toàn và không hoàn toàn; cụt không hoàn toàn không phải IS_A đứt rời hoàn toàn.",
        12: "Chỉ khâu không phải Drug; không dùng USES_DRUG cho vật liệu.",
        13: "Cắt lọc là bước của mổ nối, không phải subtype của toàn bộ quy trình.",
        18: "Làm ngắn xương là bước, không phải subtype của quy trình.",
        27: "Ghép gân và khâu gân là hai thủ thuật khác nhau; không suy IS_A.",
    }.items():
        s["edges"][f"E{i}"] = hold(reason)
    s["edges"].update(
        {
            "E6": keep(ranges=[[50, 2, 6], [58, 7, 9]]),
            "E11": keep(ranges=[[53, 0, 13]]),
            "E14": edge("N2", "N36", "MANAGED_BY", [[53, 13, 15], [54, 0, 12]]),
            "E15": edge("N34", "N41", "IS_A", [[55, 8, 11]]),
            "E17": keep(
                condition="Khi cần làm khớp; ngón thông thường được khuyên tránh đinh chéo",
                ranges=[[55, 6, 8]],
            ),
            "E19": keep(
                condition="Phác đồ trong mổ trước nối tại56.17; phân biệt các ngoại lệ sau mổ và nối chi lớn",
                ranges=[[56, 17, 18], [57, 10, 11], [57, 17, 18], [58, 2, 7]],
            ),
            "E21": edge(
                "N4",
                "N21",
                "USES_DRUG",
                [[58, 0, 2]],
                "Trường hợp khó khăn sau mổ; truyền cạnh thần kinh theo đúng điều kiện trong nguồn",
            ),
            "E24": keep(
                condition="Chỉ phần nối chi lớn, trước nối tĩnh mạch",
                ranges=[[58, 2, 7]],
            ),
        }
    )
    for i, rg in [
        (20, [[57, 8, 11], [57, 14, 17]]),
        (22, [[57, 8, 11], [57, 12, 13], [57, 15, 16]]),
        (26, [[57, 8, 11], [57, 13, 14], [57, 15, 16]]),
    ]:
        s["edges"][f"E{i}"] = keep(
            **{"from": "N4"},
            ranges=rg,
            condition="Sau mổ nối chi,7ngày; việc dùng thuốc chống đông còn được thảo luận theo nguồn",
        )
    for h, name, ranges in [
        (5, "Ngón cái (nhóm nối tốt)", [[50, 8, 10], [51, 1, 2]]),
        (6, "Một phần bàn tay (nhóm nối tốt)", [[50, 8, 9], [50, 11, 12], [51, 3, 4]]),
        (7, "Dập nát nặng (nhóm khó nối)", [[51, 4, 6]]),
        (8, "Cụt nhiều tầng (nhóm khó nối)", [[51, 4, 5], [51, 6, 7]]),
        (9, "Cụt ở người có bệnh nặng khác (nhóm khó nối)", [[51, 4, 5], [51, 7, 8]]),
    ]:
        s["held"][f"H{h}"] = recover(name, ranges)
    for h, cls, cat, rg in [
        (0, "N5", "H5", [[50, 8, 10]]),
        (1, "N5", "H6", [[50, 8, 9], [50, 11, 12]]),
        (2, "N8", "H7", [[51, 4, 6]]),
        (3, "N8", "H8", [[51, 4, 5], [51, 6, 7]]),
        (4, "N8", "H9", [[51, 4, 5], [51, 7, 8]]),
    ]:
        s["held"][f"H{h}"] = edge(cls, cat, "HAS_CATEGORY", rg)
    s["held"].update(
        {
            "H10": recover(
                "Thực hành nối mạch vi phẫu trong kíp nối chi",
                [[52, 8, 10]],
                kind="practical",
            ),
            "H11": edge("N2", "N13", "MANAGED_BY", [[52, 10, 19]]),
            "H14": edge("H10", "N2", "APPLIES_TO", [[52, 8, 10]]),
            "H28": recover(
                "Phục hồi gân trong nối chi", [[54, 0, 6], [55, 8, 20], [56, 0, 2]]
            ),
            "H30": recover(
                "Kết hợp xương bằng đinh Kirschner nội tuỷ khi nối ngón", [[55, 0, 8]]
            ),
            "H26": edge("H30", "N40", "IS_A", [[54, 17, 24], [55, 0, 8]]),
            "H39": recover(
                "Ghép tĩnh mạch để bù thiếu mạch khi nối chi", [[56, 15, 19]]
            ),
        }
    )
    s["missing"] = [
        {
            "pdf_pages": [53],
            "kind": "printed_numbering",
            "reason": "Bản in ghi Đội1 cho cả5.1 và5.2; giữ nguyên đánh số trong audit, không tự đổi thành đội2.",
        },
        {
            "pdf_pages": [57, 58],
            "kind": "conditional_regimens",
            "reason": "Heparin trong mổ, sau mổ, ca khó và nối chi lớn được giữ ở các content block riêng. Không gộp thành hướng dẫn dùng chung; giữ ngoại lệ không dùng và thời gian theo dõi.",
        },
        {
            "pdf_pages": [52],
            "kind": "unsupported_equipment_taxonomy",
            "reason": "Bảng kim/chỉ và dụng cụ có kiến thức thật nhưng không phải Drug. Giữ ngoài graph và lưu source; không mở taxonomy Device.",
        },
    ]
    return s


def lesson9():
    s, p = base(9, [59, 60])
    viewed_replacements(
        s,
        p,
        [59, 60],
        [("KHÓP", "KHỚP"), ("để hỗ", "để hở"), ("hông khớp", "hỏng khớp")],
    )
    for key, pairs in {
        "59.11": [("hay mở", "hay mổ")],
        "59.20": [("có mổ là", "có mốc là")],
        "60.0": [("Tuyên trước", "Tuyến trước")],
        "60.3": [("thì bắn", "thì bẩn"), ("bẻ mặt", "bề mặt")],
        "60.5": [("Hút gọn", "Hớt gọn")],
        "60.7": [("ĐẾN MỤN", "ĐẾN MUỘN")],
        "60.9": [("dịch dục", "dịch đục")],
        "60.11": [("cửa bỏ", "cưa bỏ"), ("chùng", "chừng")],
        "60.14": [("De dọa", "Đe dọa")],
        "60.19": [("gạc mở", "gạc mỡ")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N6": keep(ranges=[[59, 0, 5], [59, 16, 21]]),
        "N8": keep(ranges=[[59, 12, 16]]),
        "N12": keep(ranges=[[59, 19, 21], [60, 0, 7]]),
        "N17": keep(ranges=[[60, 16, 18]]),
        "N21": keep(ranges=[[60, 7, 9], [60, 11, 12]]),
        "N24": keep("Trong khớp có dịch đục loãng", [[60, 7, 10]]),
        "N26": keep(
            "Mổ rộng, tưới rửa và dẫn lưu thấp vết thương khớp háng", [[60, 16, 18]]
        ),
    }
    s["edges"] = {
        "E9": hold(
            "Không gán thủ thuật mô tả cho khớp háng sang khớp cổ chân chỉ do hai đoạn ở gần nhau."
        ),
        "E10": hold(
            "Không gán toàn bộ thủ thuật khớp háng cho khớp vai; nguồn mỗi khớp có cách bất động và dẫn lưu khác."
        ),
        "E11": keep(
            ranges=[[60, 0, 7]],
            condition="Kháng sinh ở giai đoạn đến sớm, tiếp tục7–10ngày theo nguồn",
        ),
        "E12": keep(
            ranges=[[59, 19, 21], [60, 0, 7]],
            condition="Trong24giờ; vết thương cống rãnh mới ít giờ cũng coi đến muộn",
        ),
    }
    for i in [2, 6, 8]:
        s["edges"][f"E{i}"] = keep(
            condition="Triệu chứng không đặc trưng, không tự khẳng định thấu khớp"
        )
    s["held"] = {
        "H5": merge(
            "N6", "Cùng root vết thương khớp, trích nhầm heading không làm thêm node."
        ),
        "H9": merge("N6", "Cùng root chương."),
        "H21": merge("N6", "Cùng root chương."),
        "H6": recover(
            "Phục hồi chức năng sau vết thương khớp", [[59, 4, 12], [60, 6, 7]]
        ),
        "H0": edge("N6", "N7", "GUIDED_BY", [[59, 2, 3]]),
        "H1": edge("N6", "H6", "MANAGED_BY", [[59, 4, 12]]),
        "H4": edge("N6", "N8", "CLASSIFIED_BY", [[59, 12, 16]]),
        "H7": hold(
            "Nguồn nêu mục tiêu chức năng cho bệnh nhân tập khuỷu, chưa xác lập Skill của người học."
        ),
        "H8": hold(
            "Nguồn nêu mục tiêu đi/ngồi xổm sau chấn thương gối; không tự đổi thành năng lực lâm sàng người học."
        ),
        "H22": recover(
            "Bất động bột sau xử trí vết thương khớp", [[60, 14, 18], [60, 19, 20]]
        ),
        "H19": edge(
            "N22", "H22", "MANAGED_BY", [[60, 14, 15]], "Bột bất động dạng vai"
        ),
        "H20": edge(
            "N23", "H22", "MANAGED_BY", [[60, 19, 20]], "Mổ xong băng gạc mỡ rồi bó bột"
        ),
    }
    for h, n in [(11, 24), (12, 13), (13, 25), (14, 18)]:
        s["held"][f"H{h}"] = edge(
            "N6",
            f"N{n}",
            "HAS_FINDING",
            [[60, 7, 13]],
            "Các bệnh cảnh đến muộn; không phải mọi vết thương đều có đủ các dấu hiệu",
        )
    for h, n, line, condition in [
        (15, 16, 9, "Khớp đến muộn có dịch đục loãng"),
        (16, 27, 10, "Khớp đến muộn có mủ đặc"),
        (17, 21, 11, "Có mủ kèm vỡ xương mất vững"),
        (18, 15, 12, "Viêm tấy mủ lan xa ngoài khớp, cứu tính mạng"),
    ]:
        s["held"][f"H{h}"] = edge(
            "N6", f"N{n}", "MANAGED_BY", [[60, 7, 9], [60, line, line + 1]], condition
        )
    s["missing"] = [
        {
            "pdf_pages": [59],
            "kind": "rehabilitation_skill_basis",
            "reason": "Đã giữ can thiệp phục hồi chức năng; mục tiêu bệnh nhân chưa tự biến thành Skill người học.",
        },
        {
            "pdf_pages": [60],
            "kind": "source_scope_difference",
            "reason": "Giữ riêng cấm dẫn lưu từ buồng khớp trong điều trị đến sớm và dẫn lưu thấp ở từng khớp; không nối nhầm protocol háng sang vai/cổ chân.",
        },
    ]
    return s


def lesson10():
    s, p = base(10, [61, 62])
    viewed_replacements(
        s, p, [61], [("Vì khuẩn", "Vi khuẩn"), ("vì khuẩn", "vi khuẩn")]
    )
    for key, pairs in {
        "61.3": [("dễ kháng", "đề kháng"), ("dụng đập", "đụng dập")],
        "61.4": [("lan mũ", "lan mủ")],
        "61.5": [("thì chưa khỏi", "thì chữa khỏi")],
        "61.9": [
            ("viêm mũ", "viêm mủ"),
            ("chổng gây", "chóng gây"),
            ("tiêu chòm", "tiêu chỏm"),
        ],
        "61.11": [
            ("bồng nhiền", "bỗng nhiên"),
            ("tập tành", "tập tễnh"),
            ("gập đuôi", "gập duỗi"),
        ],
        "61.13": [("đầu hiệu", "dấu hiệu"), ("xây đập", "xây đắp")],
        "61.14": [("nháp nháy", "nhấp nháy")],
        "62.2": [("Khép 2 đôi", "Khép 2 đùi")],
        "62.6": [("dục mở", "đục mở")],
    }.items():
        patch(s, p, key, *pairs)
    s["printed_marker_restorations"] = ["61.5"]
    s["nodes"] = {
        "N0": hold(
            "Tụ cầu vàng là vi khuẩn gây bệnh, không phải Condition. Schema hiện tại không có loại vi sinh vật; không ép type để nối MAY_CAUSE."
        ),
        "N3": keep("Nhấp nháy phóng xạ", [[61, 14, 15]]),
        "N5": keep(ranges=[[61, 0, 6], [61, 6, 15], [62, 0, 2]]),
        "N8": keep(
            "Viêm trật háng ở trẻ sơ sinh (bệnh án trong sách)",
            [[62, 2, 3]],
            reason="Nguồn bệnh án nói một bên háng sưng, khép đùi và nắn háng vào; tên theo đúng vị trí bệnh án, không khái quát kết quả10ngày cho mọi bệnh nhân.",
        ),
        "N10": keep("Đục mở cửa sổ xương ở hành xương", [[62, 3, 4], [62, 6, 7]]),
    }
    s["edges"] = {
        "E4": hold(
            "Tụ cầu vàng không có type thích hợp trong schema để dùng làm Condition."
        ),
        "E5": keep(condition="Rõ hơn nhưng không đặc trưng theo bản in"),
        "E6": keep(
            condition="Giai đoạn đầu có thể chưa thấy; dấu hiệu rõ muộn hơn theo nguồn"
        ),
    }
    for h, name, rg in [
        (5, "Đầu dưới xương đùi", [[61, 6, 8]]),
        (6, "Đầu trên xương chày", [[61, 6, 7], [61, 8, 9]]),
        (7, "Đầu trên xương đùi", [[61, 6, 7], [61, 9, 10]]),
        (8, "Trật khớp háng do viêm đầu trên xương đùi", [[61, 9, 10]]),
        (9, "Viêm tiêu chỏm trong viêm đầu trên xương đùi", [[61, 9, 10]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, n in [(0, 5), (1, 6), (2, 7)]:
        s["held"][f"H{h}"] = edge("N5", f"H{n}", "LOCATED_IN", [[61, 6, 10]])
    for h, n in [(3, 8), (4, 9)]:
        s["held"][f"H{h}"] = edge(
            "N5",
            f"H{n}",
            "MAY_CAUSE",
            [[61, 9, 10]],
            "Ổ viêm ở đầu trên xương đùi, phá vào khớp",
        )
    for h, n, line in [(10, 11, 4), (11, 9, 5), (12, 10, 6)]:
        s["held"][f"H{h}"] = edge(
            "N5", f"N{n}", "MANAGED_BY", [[62, 3, 4], [62, line, line + 1]]
        )
    s["held"]["H13"] = edge("N5", "N12", "EVALUATED_BY", [[62, 6, 7]])
    s["held"]["H14"] = merge(
        "N5",
        "Cùng bệnh viêm xương cấp tính được nêu tiêu đề; dùng node có mô tả đầy đủ.",
    )
    s["missing"] = [
        {
            "pdf_pages": [62],
            "kind": "printed_dose_scope",
            "reason": "Bản in ghi10–12triệu trong10–14ngày và y văn tới40triệu đơnvị1ngày, chưa rõ chu kỳ ở vế đầu. Giữ quote đúng sách, không tự điền liều/ngày hoặc cập nhật phác đồ.",
        },
        {
            "pdf_pages": [61, 62],
            "kind": "printed_typography",
            "reason": "Giữ tiêu đề Đại xương và chữ kháng trong bệnh án ở nguồn; tên node dựa vị trí háng được nêu rõ trong cùng bệnh án, chưa phải chuyên gia duyệt.",
        },
    ]
    return s


def lesson11():
    s, p = base(11, [63, 64, 65, 66])
    for key, pairs in {
        "63.17": [("bốc tách", "bóc tách")],
        "63.18": [("toàn máu", "toan máu")],
        "63.19": [("cơ đỏ ra", "cơ đờ ra")],
        "64.5": [("đập nát", "dập nát")],
        "64.6": [("vôi vẫn", "vội vã")],
        "64.7": [
            ("Vì khuẩn", "Vi khuẩn"),
            ("móng, dùi", "mông, đùi"),
            ("hoạt thư", "hoại thư"),
        ],
        "64.8": [("hoạt thư", "hoại thư")],
        "64.10": [("Viêm tẩy", "Viêm tấy")],
        "64.15": [("Viêm tẩy", "Viêm tấy")],
        "64.16": [("Dau", "Đau")],
        "64.17": [("lao xạ", "lạo xạo")],
        "65.1": [("dẫn dẫn", "dần dần"), ("suy tim mạch", "truỵ tim mạch")],
        "65.2": [("cổ ủa", "cỏ úa"), ("lao xao", "lạo xạo")],
        "65.10": [("Tiền lượng", "Tiên lượng")],
        "66.7": [("giở giơ", "giỏ giọt")],
    }.items():
        patch(s, p, key, *pairs)
    for i in [2, 3, 5, 6, 14, 18]:
        s["nodes"][f"N{i}"] = hold(
            "Đối tượng là vi khuẩn/nhóm vi khuẩn, không phải Condition. Giữ ngoài vì schema không có Microorganism, không ép thành bệnh."
        )
    for i in [8, 12, 16, 19]:
        s["nodes"][f"N{i}"] = hold(
            "Độc tố và tính chất sinh học không phải Finding lâm sàng của bệnh nhân. Giữ nguồn ngoài graph theo schema hiện tại."
        )
    s["nodes"].update(
        {
            "N0": keep("Giai đoạn toàn phát hoại thư sinh hơi", [[64, 15, 19]]),
            "N4": hold(
                "Đây là danh sách yếu tố nguy cơ/điều kiện, chưa phải ClinicalPrinciple hoặc guideline; không ép taxonomy."
            ),
            "N7": keep(ranges=[[63, 0, 4], [65, 15, 18], [66, 11, 14]]),
            "N10": merge("N7", "Cùng bệnh ở phần điều trị, không tạo thêm root."),
            "N40": merge("N7", "Cùng bệnh ở kết luận."),
            "N15": keep("Giai đoạn sớm hoại thư sinh hơi khu trú", [[64, 10, 15]]),
            "N20": keep(ranges=[[65, 4, 6], [65, 7, 8]]),
            "N22": keep(ranges=[[65, 4, 7]]),
            "N31": keep(ranges=[[65, 4, 6], [65, 8, 9]]),
            "N23": keep("Da màu nâu hoặc cỏ úa", [[65, 0, 3]]),
            "N24": keep(
                "Xử lý vết thương kỳ đầu để dự phòng hoại thư sinh hơi",
                [[65, 9, 13], [66, 13, 14]],
            ),
            "N25": keep(
                "Giai đoạn nhiễm trùng huyết và nhiễm độc trong hoại thư sinh hơi",
                [[65, 0, 3]],
                type="ClassificationCategory",
            ),
            "N29": keep("Chi phù nề, lạo xạo hơi", [[65, 0, 3]]),
            "N30": keep(
                "Kháng sinh mạnh và phối hợp để dự phòng hoại thư",
                [[65, 9, 10], [65, 13, 14]],
            ),
            "N32": keep(ranges=[[66, 3, 5]]),
            "N33": keep(ranges=[[66, 8, 11]]),
            "N34": keep(
                "Phẫu thuật điều trị hoại thư sinh hơi", [[65, 15, 18], [66, 0, 5]]
            ),
            "N36": keep("Thể viêm tấy khu trú (chỉ định bảo tồn chi)", [[66, 0, 3]]),
            "N37": merge(
                "N38",
                "Cùng mở rộng/cắt lọc để bảo tồn chi ở thể khu trú; không phải điều trị không mổ.",
            ),
            "N38": keep(
                "Phẫu thuật bảo tồn chi ở thể hoại thư khu trú",
                [[65, 17, 18], [66, 0, 3]],
            ),
            "N39": merge(
                "N24",
                "Kết luận nhắc lại dự phòng bằng xử lý kỳ đầu, cắt lọc và không đóng kín; giữ cả hai đoạn nguồn.",
            ),
        }
    )
    for i in [3, 6, 7, 8]:
        s["edges"][f"E{i}"] = hold(
            "Chiều bệnh gây ra vi khuẩn sai; chưa có type hợp lệ cho vi sinh vật nên không tự đảo chiều để nhập."
        )
    s["edges"]["E14"] = hold(
        "Giai đoạn bệnh không phải Finding; giữ Category với phạm vi nguồn riêng, thiếu Classification giai đoạn."
    )
    s["edges"]["E10"] = keep(
        condition="Dự phòng theo mục4.2, không phải phác đồ điều trị được cập nhật"
    )
    s["edges"]["E15"] = keep(condition="Dự phòng bằng xử lý vết thương kỳ đầu")
    s["edges"]["E18"] = keep(
        condition="Thể khu trú còn chỉ định bảo tồn chi",
        ranges=[[65, 17, 18], [66, 0, 3]],
    )
    s["held"] = {
        "H8": merge("N7", "Cùng root tiêu đề."),
        "H19": merge("N7", "Cùng root tiêu đề."),
        "H20": merge("N7", "Cùng root tiêu đề."),
        "H21": recover("Điều trị thuốc cho hoại thư sinh hơi", [[66, 5, 8]]),
        "H22": recover("Kháng sinh liều cao tĩnh mạch điều trị hoại thư", [[66, 5, 7]]),
        "H23": recover(
            "Điều trị toàn thân và tại chỗ hoại thư sinh hơi", [[66, 8, 11]]
        ),
        "H11": edge(
            "N7",
            "N34",
            "MANAGED_BY",
            [[65, 15, 18], [66, 0, 5]],
            "Càng sớm càng tốt, gây mê nội khí quản, không gây tê tại chỗ",
        ),
        "H12": edge("N7", "N32", "MANAGED_BY", [[66, 3, 5]], "Giai đoạn muộn"),
        "H13": edge("N7", "H21", "MANAGED_BY", [[66, 5, 8]]),
        "H14": edge("N7", "H22", "MANAGED_BY", [[66, 5, 7]]),
        "H15": edge("H21", "N35", "USES_DRUG", [[66, 5, 8]]),
        "H16": edge("N7", "H23", "MANAGED_BY", [[66, 8, 11]]),
        "H17": edge("N7", "N33", "MANAGED_BY", [[66, 8, 11]]),
    }
    for h, n, line in [(5, 22, 6), (6, 20, 7), (7, 31, 8)]:
        s["held"][f"H{h}"] = edge(
            "N7",
            f"N{n}",
            "EVALUATED_BY",
            [[65, 4, 6], [65, line, line + 1]],
            "Lâm sàng là chính; phòng thí nghiệm thường muộn",
        )
    s["missing"] = [
        {
            "pdf_pages": [63, 65, 66],
            "kind": "printed_claims_preserved",
            "reason": "Bản in ghi Gr(-), và tỷlệ tửvong20–30 thiếu đơn vị%; không tự sửa bằng kiến thức ngoài hoặc thêm ký hiệu.",
        },
        {
            "pdf_pages": [66],
            "kind": "serum_dose_frequency",
            "reason": "Giữ50.000đơnvị với500ml và3ngày300.000đơnvị như bản in, không tự suy ra số lần/ngày.",
        },
        {
            "pdf_pages": [63, 64],
            "kind": "unsupported_entity_types",
            "reason": "Vi khuẩn và độc tố có kiến thức thật nhưng không có type phù hợp; giữ toàn bộ đề xuất/nguồn ngoài graph.",
        },
    ]
    return s


def lesson12():
    s, p = base(12, list(range(67, 77)))
    viewed_replacements(
        s,
        p,
        list(range(67, 77)),
        [
            ("mũ", "mủ"),
            ("mù", "mủ"),
            ("mỡ", "mủ"),
            ("MỠ", "MỦ"),
            ("để hỗ", "để hở"),
            ("chấn mé", "chín mé"),
            ("CHÍN MẾ", "CHÍN MÉ"),
            ("bao gân gãy", "bao gân gấp"),
        ],
    )
    for key, pairs in {
        "67.12": [("làm mổ", "làm mủ"), ("thường khởi", "thường khỏi")],
        "67.13": [("có mổ", "có mủ")],
        "69.11": [("lá mồi qua", "lá mỏ quạ")],
        "70.1": [("hay gãy", "hay gặp"), ("ố áp xe", "ổ áp xe")],
        "70.13": [("ố áp xe", "ổ áp xe"), ("mủ đầy", "mủ đẩy")],
        "71.1": [("băng cấn", "băng cồn")],
        "71.11": [("đâm đâm", "dằm đâm")],
        "72.5": [("đứt gãy", "nứt kẽ")],
        "73.1": [("nếp làn da", "nếp lằn da")],
        "73.14": [("băng cotton", "băng cồn"), ("mất trật tự", "mất trượt")],
        "74.11": [("Luôn một", "Luồn một")],
    }.items():
        patch(s, p, key, *pairs)
    s["ocr"]["67.17"] = (
        "Đặt garô tốt nhất là garô hơi, phải đặt cao phía cánh tay, không dồn máu về vì vi khuẩn sẽ lan rộng."
    )
    s["nodes"] = {
        "N0": keep("Bao hoạt dịch gân gấp bàn và ngón tay", [[68, 5, 7]]),
        "N5": keep(ranges=[[69, 0, 19], [70, 0, 4]]),
        "N9": keep("Gân và xương ở bàn tay", [[68, 3, 4]]),
        "N10": keep(ranges=[[67, 0, 18], [76, 5, 13]]),
        "N12": keep(
            "Dùng kháng sinh liều cao toàn thân trong nhiễm trùng bàn tay",
            content_groups=[
                [[67, 12, 13]],
                [[72, 3, 4], [72, 14, 15]],
                [[72, 15, 16], [73, 2, 3]],
                [[73, 3, 4], [73, 10, 11]],
                [[73, 12, 13], [74, 1, 5]],
                [[76, 9, 10]],
            ],
        ),
        "N15": hold(
            "Tụ cầu vàng là vi sinh vật, không phải Finding. Không ép type vi sinh vật sang bệnh/dấu hiệu để giữ cạnh."
        ),
        "N16": keep("Đặt garô hơi khi xử trí nhiễm trùng bàn tay", [[67, 17, 18]]),
        "N22": keep("Viêm xương đốt3 do chín mé", [[70, 0, 2]]),
        "N23": merge(
            "N5", "Cùng chín mé ở phần lâm sàng/xử trí/biến chứng của cùng bài."
        ),
        "N24": keep(ranges=[[72, 3, 15]]),
        "N26": merge(
            "N48",
            "Nguồn70.3 nêu mủ tràn vào bao gân gấp, tương ứng bệnh được trình bày mục7; giữ phần biến chứng trong node chung, các subtype ngón vẫn riêng.",
        ),
        "N29": keep("Điều trị sớm viêm mủ cạnh móng", [[70, 6, 11], [71, 0, 2]]),
        "N32": keep("Viêm mủ cạnh móng và quanh móng", [[70, 6, 11]]),
        "N33": keep("Rạch tháo mủ khoang giữa gan tay", [[72, 15, 16], [73, 0, 3]]),
        "N36": keep(ranges=[[72, 15, 21], [73, 0, 3]]),
        "N39": keep("Rạch dẫn lưu mủ viêm tấy sâu kẽ ngón", [[72, 3, 4], [72, 11, 15]]),
        "N43": keep("Trích tháo mủ ô mô cái", [[73, 3, 4], [73, 8, 11]]),
        "N45": keep("Viêm khoang mô cái", [[73, 3, 11]]),
        "N46": keep("Đặt ống dẫn lưu16Fr tưới rửa ô mô cái", [[73, 3, 4], [73, 8, 11]]),
        "N48": keep(
            "Viêm mủ bao hoạt dịch gân gấp ngón tay",
            content_groups=[[[70, 3, 4]], [[73, 11, 16]], [[75, 0, 5]], [[76, 10, 11]]],
        ),
        "N50": keep(ranges=[[67, 5, 6], [75, 10, 16], [76, 0, 5]]),
        "N54": keep(
            "Mổ dẫn lưu mủ bao hoạt dịch gân gấp ngón2,3,4", [[73, 12, 13], [74, 5, 12]]
        ),
        "N55": merge(
            "N10", "Cùng nhiễm trùng bàn tay từ tiêu đề/định nghĩa và tóm tắt cuối bài."
        ),
        "N58": keep(
            "Kháng sinh cho nhiễm trùng yếm khí bàn tay", [[75, 10, 12], [76, 0, 5]]
        ),
        "N60": keep(
            "Viêm mủ bao hoạt dịch gân gấp ngón2,3,4", [[73, 12, 22], [74, 0, 12]]
        ),
        "N62": keep("Viêm mủ bao hoạt dịch gân gấp ngón1và5", [[75, 0, 9]]),
        "N64": keep(
            "Tưới rửa bao hoạt dịch gân gấp ngón2,3,4", [[73, 12, 13], [74, 10, 12]]
        ),
        "N65": merge(
            "N48",
            "Tóm tắt76.10 nhắc đúng biến chứng viêm mủ bao hoạt dịch đã trình bày mục7; không thêm bệnh mới từ lỗi OCR mô/mủ.",
        ),
    }
    for i in [35, 40, 44, 52, 61]:
        s["nodes"][f"N{i}"] = merge(
            "N12",
            "Cùng can thiệp kháng sinh toàn thân liều cao trong cùng chương; mỗi vị trí và giai đoạn được giữ ở content block riêng, không gộp thành phác đồ mới.",
        )
    s["edges"] = {
        "E2": edge("N50", "N10", "IS_A", [[75, 10, 13]]),
        "E6": keep(condition="Khi chưa làm mủ"),
        "E7": keep(condition="Viêm quá48giờ, khi đã có mủ"),
        "E9": keep(condition="Khi không gây mê toàn thân; không phải gây tê tại chỗ"),
        "E16": keep(condition="Nếu chín mé không được thoát mủ"),
        "E32": hold(
            "Trích74.2 thuộc ngón2,3,4 trước làm mủ, không gán sang viêm mủ ngón1và5."
        ),
        "E34": keep(ranges=[[74, 5, 12]], condition="Sau48giờ khi đã làm mủ"),
        "E35": keep(condition="Khi có mủ"),
        "E37": keep(ranges=[[74, 1, 5]], condition="Khi chưa làm mủ,24–48giờ đầu"),
        "E38": keep(ranges=[[74, 10, 12]]),
        "E40": hold(
            "Không gán đường mổ ngón2,3,4 cho bao hoạt dịch quay/trụ ngón1và5; nguồn có hai kỹ thuật riêng."
        ),
    }
    for h, name, rg in [
        (14, "Sưng đau kẽ ngón và gan tay", [[72, 7, 9]]),
        (15, "Ngón dạng rộng như càng cua", [[72, 7, 10]]),
        (16, "Da mu tay sưng nề trong viêm tấy kẽ ngón", [[72, 7, 11]]),
        (27, "Sưng to rất đau ô mô cái", [[73, 6, 8]]),
        (28, "Hạn chế cơ năng ngón cái", [[73, 6, 8]]),
        (29, "Bùng nhùng mủ ô mô cái", [[73, 6, 8]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, n, frm in [
        (10, 14, "N24"),
        (11, 15, "N24"),
        (12, 16, "N24"),
        (18, 27, "N45"),
        (19, 28, "N45"),
        (20, 29, "N45"),
    ]:
        s["held"][f"H{h}"] = edge(
            frm, f"H{n}", "HAS_FINDING", [[72, 7, 11]] if frm == "N24" else [[73, 6, 8]]
        )
    s["held"].update(
        {
            "H8": edge(
                "N32", "N31", "MANAGED_BY", [[71, 4, 5]], "Chăm sóc sau mổ cạnh móng"
            ),
            "H26": recover(
                "Viêm bao hoạt dịch gân gấp ngón1,2 gây viêm ô mô cái", [[73, 3, 6]]
            ),
            "H17": edge("H26", "N45", "MAY_CAUSE", [[73, 3, 6]]),
            "H21": edge("N60", "N10", "IS_A", [[67, 0, 3], [73, 11, 13]]),
            "H22": edge("N48", "N10", "IS_A", [[67, 0, 3], [73, 11, 13]]),
            "H23": edge("N60", "N48", "IS_A", [[73, 11, 13]]),
            "H24": edge(
                "N5", "N60", "MAY_CAUSE", [[73, 12, 16]], "Viêm mủ lân cận tràn vào"
            ),
            "H25": edge(
                "N53", "N60", "MAY_CAUSE", [[73, 12, 16]], "Viêm mủ lân cận tràn vào"
            ),
            "H30": merge("N10", "Cùng root tiêu đề."),
            "H31": merge("N60", "Cùng subtype ngón2,3,4 đã có mô tả lâm sàng."),
            "H32": merge("N5", "Cùng chín mé nêu là nguồn lan nhiễm vào bao gân."),
            "H33": merge(
                "N53",
                "Cùng viêm xương khớp bàn tay được nhắc trong nguyên nhân và kết luận.",
            ),
            "H37": recover("Hoại thư sinh hơi ở bàn tay", [[75, 10, 13]]),
            "H38": recover("Metronidazon (tên trong bản in)", [[76, 0, 4]]),
            "H39": recover(
                "Cắt cụt chi cứu sống người nhiễm yếm khí bàn tay", [[76, 0, 5]]
            ),
            "H34": edge(
                "N50",
                "H39",
                "MANAGED_BY",
                [[76, 0, 5]],
                "Nhiều trường hợp nặng cần cứu tính mạng",
            ),
            "H35": edge(
                "N58",
                "H38",
                "USES_DRUG",
                [[76, 3, 4]],
                "Ví dụ thuốc được nêu trong bản in",
            ),
        }
    )
    s["missing"] = [
        {
            "pdf_pages": [71, 72],
            "kind": "caption_text_discrepancy",
            "reason": "Đã xem hình12.8: caption nói lấy một phần gốc móng/cả móng, đoạn điều trị dặn giữ gốc để móng mọc. Giữ riêng nguồn, không tự chọn bên nào thay sách.",
        },
        {
            "pdf_pages": [67, 71],
            "kind": "source_anesthesia_scope",
            "reason": "Nguyên tắc chung cấm gây tê tại chỗ nhưng mục mủ cạnh móng lại ghi gây tê. Giữ mỗi đoạn đúng phạm vi và đưa khác biệt cho người dùng xem, không tự hợp nhất thành chỉ định mới.",
        },
        {
            "pdf_pages": [75],
            "kind": "model_omitted_procedures",
            "reason": "Đường mổ dẫn lưu riêng cho ngón1và5/baoquay-trụ chưa có node độc lập phù hợp; giữ ngoài cạnh gán nhầm từ phương pháp ngón2,3,4.",
        },
        {
            "pdf_pages": [73, 75],
            "kind": "source_finger_scope",
            "reason": "Mục mô cái nguồn ghi ngón1,2, còn mục7.2 ghi ngón1và5. Không sửa số ngón theo kiến thức ngoài.",
        },
    ]
    return s


def lesson13():
    s, p = base(13, list(range(77, 83)))
    viewed_replacements(
        s,
        p,
        list(range(77, 83)),
        [
            ("Bóng", "Bỏng"),
            ("bóng", "bỏng"),
            ("BÓNG", "BỎNG"),
            ("sóc bỏng", "sốc bỏng"),
            ("dẫn dẫn", "dần dần"),
        ],
    )
    for key, pairs in {
        "79.4": [("Hai đầu", "Hai đùi")],
        "79.9": [("khởi", "khỏi"), ("dễ lại sẹo", "để lại sẹo")],
        "79.11": [("khởi", "khỏi"), ("dễ lại sẹo", "để lại sẹo")],
        "79.13": [
            ("Thường tổn", "Thương tổn"),
            ("khởi", "khỏi"),
            ("dễ lại sẹo", "để lại sẹo"),
        ],
        "79.15": [("dễ lại sẹo dúng đó", "để lại sẹo dúm dó")],
        "79.19": [("thăm họa", "thảm họa"), ("chỗ khách", "chở khách")],
        "80.10": [("về mặt", "vẻ mặt")],
        "80.11": [("giảm vào tổ chức", "ngấm vào tổ chức")],
        "80.12": [("dự trữ kiêm", "dự trữ kiềm")],
        "80.13": [
            ("Để bị viêm thận", "Dễ bị viêm thận"),
            ("đỏ đặc", "đỏ đục"),
            ("dái ra", "đái ra"),
        ],
        "80.16": [
            ("lo mờ", "lơ mơ"),
            ("thờ nhanh", "thở nhanh"),
            ("đi tiểu lỏng", "đi ỉa lỏng"),
        ],
        "81.12": [("đông viên", "đông miên")],
        "81.13": [("Bệnh nhỏ", "Bỏng nhỏ")],
        "82.9": [("Nốt phòng nước", "Nốt phỏng nước")],
        "82.12": [("sèo", "sẹo")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N6": keep("Xử trí bỏng do nhiệt", [[77, 10, 16]]),
        "N7": keep(ranges=[[77, 0, 9]]),
        "N10": keep("Bỏng do nhiệt", [[77, 10, 16]]),
        "N11": merge("N7", "Cùng bệnh bỏng của tiêu đề và định nghĩa."),
        "N12": keep("Luật9 của Wallace tính diện tích bỏng", [[78, 13, 24]]),
        "N14": keep("Phân loại bỏng do nhiệt", [[77, 16, 20], [78, 0, 4]]),
        "N18": keep("Bỏng do nhiệt khô", [[77, 17, 20], [78, 0, 2]]),
        "N19": merge(
            "N18", "Cùng category nhiệt khô, cùng phân loại nguyên nhân nhiệt."
        ),
        "N20": keep("Tiên lượng bỏng", [[80, 2, 8]]),
        "N21": keep("Bỏng sâu", [[79, 14, 21]]),
        "N22": keep("Bỏng nông", [[79, 9, 14]]),
        "N23": keep("Bỏng trung gian", [[80, 0, 2]]),
        "N34": keep("Sốc bỏng", [[80, 9, 15]]),
        "N36": keep("Bỏng nặng giai đoạn nhiễm trùng", [[81, 2, 6]]),
        "N37": keep("Nhiễm độc cấp tính do bỏng nặng", [[80, 15, 18], [81, 0, 2]]),
        "N39": keep("Điều trị bỏng", content_groups=[[[80, 14, 15]], [[81, 0, 2]]]),
        "N40": hold(
            "Diễn biến lâm sàng là tiêu đề trình bày, không phải một Condition. Không tạo bệnh từ tiêu đề."
        ),
        "N42": keep("Điều trị cấp cứu ban đầu bỏng", [[81, 10, 17]]),
        "N43": keep(
            "Giai đoạn4 bỏng: hồi phục hoặc suy kiệt",
            [[81, 6, 10]],
            type="ClassificationCategory",
        ),
        "N46": keep(
            "Ngâm nước mát hoặc nước đá trong bỏng nhỏ ở chi trên", [[81, 11, 14]]
        ),
        "N48": keep("Giảm đau ban đầu cho người lớn bị bỏng", [[81, 11, 13]]),
        "N49": keep(
            "Truyền dịch và theo dõi trong sốc bỏng",
            content_groups=[[[81, 17, 22]], [[82, 6, 7]]],
        ),
        "N50": keep(
            "Điều trị toàn thân bỏng theo giai đoạn",
            content_groups=[[[81, 17, 22], [82, 6, 7]], [[82, 13, 15]], [[82, 17, 19]]],
        ),
        "N51": merge(
            "N34", "Cùng sốc bỏng của giai đoạn2ngày đầu; không tạo root bỏng thứ hai."
        ),
        "N52": keep("Vá da mỏng tự thân sau2tuần ở bỏng", [[82, 17, 18]]),
        "N53": keep(
            "Điều trị tại chỗ bỏng theo giai đoạn",
            content_groups=[[[82, 7, 13]], [[82, 13, 17]]],
        ),
        "N55": keep("Theo dõi bệnh nhân truyền dịch trong sốc bỏng", [[81, 19, 22]]),
    }
    s["edges"] = {
        "E17": edge(
            "N34",
            "N47",
            "MAY_CAUSE",
            [[80, 9, 14]],
            "Trong sốc bỏng, mất nước huyết tương và rối loạn tuần hoàn",
        ),
        "E19": edge("N7", "N39", "MANAGED_BY", [[80, 14, 15], [81, 0, 2]]),
        "E21": edge(
            "N7",
            "N37",
            "MAY_CAUSE",
            [[80, 8, 10], [80, 15, 18], [81, 0, 2]],
            "Bỏng nặng, giai đoạn nhiễm độc cấp tính",
        ),
        "E22": edge(
            "N7", "N34", "MAY_CAUSE", [[80, 8, 15]], "Bỏng nặng, giai đoạn48giờ đầu"
        ),
        "E23": hold(
            "Giai đoạn4 có thể hồi phục HOẶC suy kiệt; không phải IS_A suy kiệt."
        ),
        "E25": keep(condition="Sau2tuần"),
        "E26": keep(
            condition="Trong2ngày đầu sốc bỏng; chỉ áp dụng block giai đoạn này"
        ),
        "E28": keep(condition="Sau2tuần"),
        "E29": keep(
            condition="Điều trị tại chỗ trong2ngày đầu; không kéo cả giai đoạn sau vào sốc"
        ),
    }
    s["held"] = {
        "H8": merge("N9", "Cùng nhiệt ướt trong phân loại bỏng do nhiệt."),
        "H16": merge("N10", "Cùng bỏng nhiệt trong phần tiên lượng."),
        "H17": merge("N7", "Cùng root bỏng."),
        "H18": merge("N27", "Cùng phân loại độ sâu."),
        "H27": merge("N7", "Cùng root bỏng."),
        "H28": recover("Morphin", [[81, 11, 13]]),
        "H29": recover(
            "Uống nước đường pha bicacbonat natri trong cấp cứu bỏng",
            [[81, 11, 12], [81, 14, 15]],
        ),
        "H30": recover("Bicacbonat natri uống trong cấp cứu bỏng", [[81, 14, 15]]),
        "H31": recover(
            "Điều trị2ngày đầu giai đoạn sốc bỏng", [[81, 17, 22], [82, 6, 7]]
        ),
        "H35": recover("Ringer lactat", [[82, 2, 5]]),
        "H36": recover("Dung dịch bicacbonat natri12,5% (bản in)", [[82, 2, 5]]),
    }
    for h, left, right, rel, rg in [
        (0, "N14", "N9", "HAS_CATEGORY", [[77, 16, 18], [78, 2, 4]]),
        (2, "N14", "N18", "HAS_CATEGORY", [[77, 16, 20]]),
        (3, "N14", "N9", "HAS_CATEGORY", [[78, 2, 4]]),
        (9, "N32", "N22", "IS_A", [[79, 9, 12]]),
        (10, "N30", "N22", "IS_A", [[79, 9, 14]]),
        (11, "N33", "N21", "IS_A", [[79, 14, 18]]),
        (12, "N28", "N21", "IS_A", [[79, 14, 21]]),
        (13, "N7", "N27", "CLASSIFIED_BY", [[79, 8, 10]]),
        (14, "N27", "N23", "HAS_CATEGORY", [[79, 8, 10], [80, 0, 2]]),
        (15, "N10", "N20", "GUIDED_BY", [[80, 2, 8]]),
        (19, "N36", "N35", "MAY_CAUSE", [[81, 2, 6]]),
        (20, "N7", "N42", "MANAGED_BY", [[81, 10, 17]]),
        (21, "N7", "H31", "MANAGED_BY", [[81, 17, 22]]),
        (23, "N48", "H28", "USES_DRUG", [[81, 11, 13]]),
        (25, "N7", "H29", "MANAGED_BY", [[81, 11, 12], [81, 14, 15]]),
        (26, "H29", "H30", "USES_DRUG", [[81, 14, 15]]),
        (33, "N49", "H35", "USES_DRUG", [[82, 2, 5]]),
        (34, "N49", "H36", "USES_DRUG", [[82, 2, 5]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["missing"] = [
        {
            "pdf_pages": [82],
            "kind": "printed_fluid_units",
            "reason": "Công thức Evans và các phân số dịch: bản in dòng82.5 dừng ở9, thiếu đơn vị; không tự bổ sung nồng độ/đơn vị. Giữ ngoài block hướng dẫn truyền dịch phần công thức chưa rõ. Bicacbonat12,5% giữ đúng bản in, không đổi thành phác đồ hiện hành.",
        },
        {
            "pdf_pages": [79],
            "kind": "model_omission",
            "reason": "Bảng diện tích bỏng trẻ em và cách tính gan bàn tay không có đề xuất node đủ ngữ nghĩa độc lập; không tự tạo mới từ tiêu đề.",
        },
        {
            "pdf_pages": [77, 79, 80, 81],
            "kind": "historical_thresholds",
            "reason": "Ngưỡng diện tích/độ sâu và nước đá giữ đúng sách2006 theo từng đoạn, không hợp nhất thành hướng dẫn y khoa hiện hành.",
        },
    ]
    return s


def lesson14():
    s, p = base(14, list(range(83, 89)))
    for key, pairs in {
        "83.14": [("Osteosarcoma", "Osteosarcome")],
        "83.15": [("Chondrosarcoma", "Chondrosarcome")],
        "83.20": [("U xương,", "U xơ,")],
        "84.21": [("Dau", "Đau")],
        "84.22": [("cần thận", "cẩn thận"), ("chỉ là dị", "chỉ là dịp")],
        "84.27": [("đau môi", "đau mỏi")],
        "85.4": [("cà phê sẫm", "cà phê sữa"), ("loạn sản xương", "loạn sản xơ")],
        "85.6": [("cứng ở", "căng ở"), ("tính mạch", "tĩnh mạch")],
        "85.10": [
            ("cân quang", "cản quang"),
            ("đậm vơi", "đậm vôi"),
            ("phần ứng", "phản ứng"),
            ("phát hủy", "phá huỷ"),
            ("máy chỗ", "mấy chỗ"),
        ],
        "86.6": [("khác phục", "khắc phục")],
        "86.9": [("U xương xương đùi", "U xơ xương đùi")],
        "88.11": [("Lắp đầy", "Lấp đầy")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": keep("U xương ác tính (Osteosarcome)", [[83, 13, 15]]),
        "N2": keep("Loại trung gian của u từ tế bào cấu trúc cơ bản", [[83, 16, 19]]),
        "N3": keep(ranges=[[83, 6, 19]]),
        "N6": keep(ranges=[[83, 19, 21], [84, 0, 4]]),
        "N7": keep("Ác tính trong nhóm u từ tế bào cấu trúc cơ bản", [[83, 13, 16]]),
        "N9": keep(
            "Phân loại u xương theo tổ chức Y tế thế giới (bản2006)",
            [[83, 5, 21], [84, 0, 6]],
        ),
        "N11": keep("U sụn ác tính (Chondrosarcome)", [[83, 13, 16]]),
        "N13": keep(ranges=[[84, 6, 17]]),
        "N15": keep("Sarcome xương", [[84, 6, 17], [86, 2, 4], [88, 5, 6]]),
        "N19": keep(ranges=[[85, 7, 16]]),
        "N23": keep(
            "U xương ác tính",
            content_groups=[
                [[84, 24, 25]],
                [[85, 15, 16]],
                [[86, 5, 8]],
                [[88, 12, 23]],
            ],
        ),
        "N25": merge("N4", "Cùng bệnh u xương tại phần chẩn đoán."),
        "N29": keep("Loạn sản xơ Recklinghausen", [[85, 4, 5]]),
        "N30": keep(ranges=[[84, 0, 2], [84, 27, 28], [88, 17, 19]]),
        "N36": keep(ranges=[[86, 4, 8]]),
        "N38": keep("Xét nghiệm phosphatase kiềm", [[88, 5, 6]]),
        "N39": keep("Xét nghiệm tốc độ máu lắng", [[88, 5, 6]]),
        "N43": keep("Điều trị tia u xương ác tính", [[88, 17, 19]]),
        "N46": keep("Phẫu thuật u xương ác tính", [[88, 12, 17]]),
    }
    for i in [22, 41, 42, 47]:
        s["nodes"][f"N{i}"] = merge(
            "N23",
            "Cùng nhóm u xương ác tính trong bài; giữ từng content block, không gộp với Osteosarcome cụ thể.",
        )
    s["nodes"]["N33"] = merge(
        "N15",
        "Cùng sarcome xương ở phần xét nghiệm; không đồng nhất mọi u ác tính với osteosarcome.",
    )
    s["nodes"]["N44"] = merge("N31", "Cùng nhóm u xương lành tính ở phần điều trị.")
    s["edges"] = {
        "E14": hold(
            "Vết cà phê sữa chỉ gợi ý loạn sản xơ, không chứng minh bệnh này IS_A u xương."
        ),
        "E8": keep(condition="Có thể gặp nhưng hiếm; nếu có thì đã quá muộn theo sách"),
        "E17": keep(
            condition="Có thể gặp nhưng hiếm; nếu có thì đã quá muộn theo sách"
        ),
    }
    for h, target in [
        (15, "N9"),
        (16, "N3"),
        (18, "N31"),
        (20, "N10"),
        (31, "N4"),
        (32, "N9"),
        (33, "N6"),
        (36, "N30"),
        (40, "N4"),
        (41, "N9"),
        (49, "N4"),
        (50, "N15"),
        (62, "N10"),
        (63, "N28"),
        (68, "N30"),
    ]:
        s["held"][f"H{h}"] = merge(
            target,
            "Đối chiếu đúng cùng đối tượng và ngữ cảnh trong bài; hợp nguồn, không sinh node trùng.",
        )
    for h, name, rg in [
        (17, "Lành tính trong nhóm u từ tế bào cấu trúc cơ bản", [[83, 7, 13]]),
        (19, "U sụn lành tính", [[83, 7, 11]]),
        (21, "U nang xương đơn độc ở thiếu nhi", [[83, 7, 13], [88, 11, 12]]),
        (34, "Lành tính trong nhóm u từ tủy xương", [[83, 19, 21]]),
        (35, "Ác tính trong nhóm u từ tủy xương", [[83, 19, 20], [84, 0, 4]]),
        (37, "Sarcoma mạng lưới", [[84, 0, 3]]),
        (38, "Sarcoma lympho", [[84, 0, 1], [84, 3, 4]]),
        (39, "U từ phần mềm thâm nhập vào xương", [[84, 4, 5]]),
        (42, "Khám thực thể u xương", [[85, 1, 7]]),
        (51, "Tốc độ máu lắng tăng cao", [[86, 2, 4]]),
        (52, "Phosphataza kiềm tăng", [[86, 2, 4]]),
        (65, "Đục bỏ u xương sụn", [[88, 7, 10]]),
        (
            66,
            "Lấy bỏ khối u và đoạn xương rồi ghép xương ở u tế bào khổng lồ",
            [[88, 7, 9], [88, 10, 11]],
        ),
        (
            67,
            "Lấp đầy nang xương bằng xương tự thân hay đồng loại",
            [[88, 7, 9], [88, 11, 12]],
        ),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    s["held"]["H64"] = merge(
        "H21", "Cùng nang xương đơn độc ở thiếu nhi, nguồn phân loại và điều trị."
    )
    s["held"]["H42"]["kind"] = "practical"
    for h, left, right, rel, rg in [
        (0, "N4", "N9", "CLASSIFIED_BY", [[83, 5, 6]]),
        (1, "N9", "N3", "HAS_CATEGORY", [[83, 5, 7]]),
        (22, "N4", "N9", "CLASSIFIED_BY", [[83, 0, 1], [83, 5, 6]]),
        (23, "N9", "N6", "HAS_CATEGORY", [[83, 5, 6], [83, 19, 20]]),
        (29, "N12", "N4", "IS_A", [[84, 5, 6]]),
        (30, "N4", "N9", "CLASSIFIED_BY", [[83, 5, 6]]),
        (43, "H42", "N4", "APPLIES_TO", [[85, 1, 7]]),
        (44, "N4", "N27", "EVALUATED_BY", [[85, 16, 18]]),
        (45, "N4", "N21", "EVALUATED_BY", [[86, 0, 2]]),
        (46, "N4", "N18", "EVALUATED_BY", [[86, 2, 4]]),
        (47, "N15", "H51", "HAS_FINDING", [[86, 2, 4]]),
        (48, "N15", "H52", "HAS_FINDING", [[86, 2, 4]]),
        (53, "N4", "N40", "HAS_FINDING", [[88, 0, 3]]),
        (54, "N4", "N35", "HAS_FINDING", [[88, 0, 3]]),
        (55, "N10", "H65", "MANAGED_BY", [[88, 7, 10]]),
        (56, "N28", "H66", "MANAGED_BY", [[88, 7, 9], [88, 10, 11]]),
        (57, "H21", "H67", "MANAGED_BY", [[88, 7, 9], [88, 11, 12]]),
        (61, "N30", "N43", "MANAGED_BY", [[88, 17, 19]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["missing"] = [
        {
            "pdf_pages": [83, 84],
            "kind": "classification_schema_limit",
            "reason": "Cây WHO bản2006 lồng nhiều trục nguồn gốc/lành ác/trung gian; Category không được làm cha HAS_CATEGORY. Giữ đủ nguồn trên category, các cạnh lồng sai schema và bullet U xương mơ hồ để ngoài; không phát minh Classification mới.",
        },
        {
            "pdf_pages": [84, 88],
            "kind": "historical_system",
            "reason": "TNM Ott/Hamzey1970 và chỉ dẫn phẫu thuật/tia giữ theo bản in, chưa cập nhật staging hoặc chuẩn điều trị mới.",
        },
    ]
    return s


def lesson16():
    s, p = base(16, list(range(93, 98)))
    viewed_replacements(
        s,
        p,
        list(range(93, 98)),
        [
            ("mòn vệt", "mỏm vẹt"),
            ("mềm vẹt", "mỏm vẹt"),
            ("móm", "mỏm"),
            ("môm", "mỏm"),
            ("lỗi cầu", "lồi cầu"),
            ("đuôi", "duỗi"),
            ("gây chòm", "gãy chỏm"),
            ("chòm quay", "chỏm quay"),
        ],
    )
    for key, pairs in {
        "93.0": [("KHÓP KHUYU", "KHỚP KHUỶU")],
        "93.6": [("hốc xích", "hõm xích")],
        "93.8": [("hốc xích", "hõm xích")],
        "94.8": [("sở thấy", "sờ thấy")],
        "94.9": [
            ("Sở", "Sờ"),
            ("sở phía", "sờ phía"),
            ("gấp chùng", "gấp chừng"),
            ("gân cơ tam đầu càng", "gân cơ tam đầu căng"),
        ],
        "94.10": [("Sở được", "Sờ được")],
        "94.11": [("bất mạch", "bắt mạch")],
        "94.12": [
            ("đập", "dập"),
            ("sau chấn trật", "sau nắn trật"),
            ("mạch hiến", "mạch hiển"),
        ],
        "94.13": [("đụng đập", "đụng dập"), ("sau chấn", "sau nắn")],
        "95.6": [
            ("thông bàn", "thõng bàn"),
            ("mềm khuỷu", "mỏm khuỷu"),
            ("có vũng", "có vững"),
        ],
        "95.8": [("Gãy mô", "Gây mê")],
        "95.23": [("nẹp ép", "néo ép")],
        "96.0": [("kèm gây", "kèm gãy")],
        "96.6": [("mạnh gãy", "mảnh gãy"), ("võ mạnh", "vỡ mảnh")],
        "97.0": [("bất vị", "bắt vít")],
        "97.4": [("dười", "duỗi")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N4": keep(ranges=[[93, 0, 17], [94, 0, 14], [95, 1, 12]]),
        "N7": keep("Colton kiểu2: gãy mỏm khuỷu di lệch", [[95, 14, 22]]),
        "N8": keep("Phân loại Colton gãy mỏm khuỷu", [[95, 14, 22]]),
        "N9": keep(
            "Colton kiểu1: gãy mỏm khuỷu không lệch hoặc lệch ít", [[95, 14, 17]]
        ),
        "N10": keep("Phân loại Mason gãy chỏm quay", [[96, 7, 14]]),
        "N13": keep(
            "Trật khuỷu kèm gãy chỏm xương quay",
            [[96, 7, 15], [97, 0, 3]],
            reason="Các cạnh trong cửa sổ này thuộc riêng phần gãy chỏm quay96.7, không dùng tiêu đề gãy xương chung95.12 để mở rộng chỉ định.",
        ),
        "N15": merge("N4", "Cùng trật khuỷu trong cùng bài."),
        "N16": keep("Phân loại Reagan gãy mỏm vẹt", [[96, 0, 6]]),
        "N17": keep(
            "Mổ kết hợp xương mỏm khuỷu theo phương pháp Haubanage", [[95, 14, 24]]
        ),
        "N20": keep(ranges=[[95, 3, 10]]),
        "N34": hold(
            "Nguyên nhân/cơ chế chấn thương không phải ClinicalPrinciple. Giữ cơ chế trên nội dung bệnh, không gán GUIDED_BY."
        ),
        "N39": keep(ranges=[[97, 3, 6]]),
        "N42": keep("Mổ cố định gãy mỏm vẹt", [[96, 0, 7]]),
        "N43": keep("Trật khuỷu kèm gãy mỏm vẹt", [[96, 0, 7]]),
    }
    for i in [4, 11, 21]:
        s["edges"][f"E{i}"] = hold(
            "Quan hệ giải phẫu thành phần không phải IS_A; schema không có HAS_PART, không đảo chiều thành phân loại."
        )
    s["edges"].update(
        {
            "E7": keep(condition="Kèm gãy mỏm khuỷu không lệch", ranges=[[95, 14, 23]]),
            "E10": keep(
                condition="Áp dụng khi kèm gãy mỏm khuỷu", ranges=[[95, 14, 22]]
            ),
            "E9": keep(condition="Trật khuỷu mới", ranges=[[95, 3, 7]]),
            "E15": keep(
                condition="Gây mê không nắn vào được: kẹt khớp, gãy xương nội khớp hoặc chèn phần mềm"
            ),
            "E23": hold("Không dùng cơ chế ngã như nguyên tắc hướng dẫn."),
            "E31": keep(
                condition="Kèm gãy mỏm khuỷu có di lệch", ranges=[[95, 14, 24]]
            ),
            "E25": keep(
                condition="Trật khớp quá lâu; nguồn chỉ định làm cứng ở tư thế cơ năng"
            ),
            "E27": keep(
                condition="Kèm gãy mỏm trên lồi cầu trong, mảnh kẹt khớp; chỉ định sau kiểm tra Xquang",
                ranges=[[95, 12, 14]],
            ),
        }
    )
    for h, name, rg in [
        (10, "Phân loại trật khớp khuỷu theo hướng", [[94, 2, 6]]),
        (11, "Reagan kiểu1: bong xương ở đỉnh mỏm vẹt", [[96, 0, 3]]),
        (12, "Reagan kiểu2 (bản in: gãy xương rời ra50%)", [[96, 1, 4]]),
        (13, "Reagan kiểu3 (bản in: gãy xương rời ra50%)", [[96, 1, 2], [96, 4, 5]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, left, right, rel, rg in [
        (0, "N4", "H10", "CLASSIFIED_BY", [[94, 2, 6]]),
        (1, "H10", "N29", "HAS_CATEGORY", [[94, 3, 4]]),
        (2, "H10", "N30", "HAS_CATEGORY", [[94, 4, 5]]),
        (3, "H10", "N22", "HAS_CATEGORY", [[94, 5, 6]]),
        (4, "N41", "N14", "MANAGED_BY", [[94, 13, 14]]),
        (5, "N4", "N37", "HAS_FINDING", [[95, 10, 12]]),
        (6, "N4", "N35", "HAS_FINDING", [[95, 10, 12]]),
        (7, "N16", "H11", "HAS_CATEGORY", [[96, 1, 3]]),
        (8, "N16", "H12", "HAS_CATEGORY", [[96, 1, 4]]),
        (9, "N16", "H13", "HAS_CATEGORY", [[96, 1, 2], [96, 4, 5]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["held"]["H4"]["condition"] = "Liệt quá3tháng: thăm dò; liệt sau nắn: thăm dò ngay"
    s["held"]["H5"]["condition"] = "Sau nắn, dễ cứng khớp hơn mất vững"
    s["held"]["H6"]["condition"] = "Sau nắn, ít hơn cứng khớp theo so sánh trong nguồn"
    s["missing"] = [
        {
            "pdf_pages": [96],
            "kind": "printed_classification_ambiguity",
            "reason": "Đã xem hình16.3: cả dòng kiểu2 và3 đều in50%, không có dấu nhỏ/lớn. Giữ đúng hai dòng và hình riêng, không tự bổ sung < hoặc > theo trí nhớ.",
        },
        {
            "pdf_pages": [95],
            "kind": "source_typography",
            "reason": "Frenkel3 giữ nguyên bản in; không thay bằng hệ chấm sức cơ khác. Không bổ sung thuốc cho mục Vô cảm chỉ có tiêu đề.",
        },
    ]
    return s


def lesson17():
    s, p = base(17, list(range(98, 105)))
    viewed_replacements(
        s,
        p,
        list(range(98, 105)),
        [
            ("chòm", "chỏm"),
            ("ổ cồi", "ổ cối"),
            ("ổ cốt", "ổ cối"),
            ("máu chuyển", "mấu chuyển"),
            ("dạn dập", "đụng dập"),
        ],
    )
    for key, pairs in {
        "98.5": [("hông", "mông")],
        "100.1": [("xương dài", "xương đùi"), ("gấp85", "gặp85"), ("gấp 85", "gặp 85")],
        "100.2": [("xương dài", "xương đùi")],
        "100.3": [("Kiểu ngôi", "Kiểu ngồi"), ("xương dài", "xương đùi")],
        "100.4": [("xương dài", "xương đùi")],
        "100.5": [("xương dài", "xương đùi"), ("ổ cổ vớ", "ổ cối vỡ")],
        "100.7": [("chấn", "nắn")],
        "100.8": [("ổ cổ", "ổ cối"), ("chấn", "nắn")],
        "100.10": [("xương dài", "xương đùi")],
        "100.15": [("ngôi", "ngồi"), ("dài khớp", "đùi khép")],
        "100.16": [("dài dạng", "đùi dạng")],
        "100.17": [("dài gấp", "đùi gấp")],
        "100.18": [("ngôi", "ngồi"), ("dài gấp", "đùi gấp")],
        "101.1": [
            ("chỏm bit", "chỏm bị"),
            ("cổ bit", "cổ bịt"),
            ("xương dùi", "xương đùi"),
            ("vì dùi", "vì đùi"),
        ],
        "101.2": [("sút vỡ", "sứt vỡ")],
        "101.7": [("can xương", "can xấu")],
        "101.13": [
            ("lần thì", "lần thôi"),
            ("Gãy mê", "Gây mê"),
            ("gãy mê", "gây mê"),
            ("xương dùi", "xương đùi"),
        ],
        "101.14": [("màng", "mày"), ("mạnh vỡ", "mảnh vỡ")],
        "101.15": [("lối cầu dùi", "lồi cầu đùi")],
        "102.0": [("Gây nặng", "Gãy nặng")],
        "102.2": [("xương dài", "xương đùi"), ("rách viễn ở cổ", "rách viền ổ cối")],
        "102.6": [("đai chân", "đai chậu")],
        "102.9": [
            ("thẳng dài", "thẳng đùi"),
            ("để căng", "đè cẳng"),
            ("khớp háng", "khép háng"),
        ],
        "103.1": [
            ("thẳng2", "thõng2"),
            ("thẳng 2", "thõng 2"),
            ("gồi", "gối"),
            ("cố người", "có người"),
            ("cùng dẫn", "chùng dần"),
            ("kéo dài", "kéo đùi"),
        ],
        "103.8": [("hông khớp", "hõm khớp")],
        "103.13": [("ố cổ", "ổ cối")],
        "103.14": [("ở cổ", "ổ cối")],
        "104.0": [("chừa khỏi", "chỏm ra khỏi"), ("lỗ cầu đủ", "lồi cầu đùi")],
        "104.3": [("nắn thủ", "nắn thử")],
        "104.5": [("dục xương", "đục xương")],
    }.items():
        # Some literal variants are absent depending on spacing in the OCR.
        pairs = [
            (a, b)
            for a, b in pairs
            if a
            in s["ocr"].get(
                key,
                p[int(key.split(".")[0])]["raw_text"].splitlines()[
                    int(key.split(".")[1])
                ],
            )
        ]
        if pairs:
            patch(s, p, key, *pairs)
    s["nodes"] = {
        "N4": keep(ranges=[[98, 0, 11], [99, 0, 23], [100, 0, 19]]),
        "N8": hold(
            "Tai nạn xe là hoàn cảnh/cơ chế, không phải Condition; giữ trong nội dung bệnh thay vì MAY_CAUSE với type sai."
        ),
        "N18": keep("Kiểu ngồi", [[100, 3, 4]]),
        "N20": keep("Cơ vùng đùi và chậu đụng dập, tụ máu", [[99, 19, 20]]),
        "N22": keep(
            "Tổn thương xương, dây chằng và bao khớp trong trật háng", [[99, 14, 19]]
        ),
        "N26": merge(
            "N5", "Cùng hoại tử chỏm sau trật háng; hợp nguồn di chứng và biến chứng."
        ),
        "N28": keep("Thoái hoá khớp háng sau trật trung tâm", [[101, 7, 8]]),
        "N33": keep("Mổ thay chỏm ở trật háng kèm vỡ chỏm", [[102, 1, 2]]),
        "N34": keep(ranges=[[103, 0, 3]]),
        "N37": keep(
            "Mổ nắn và kết hợp xương trong trật háng kèm tổn thương xương",
            content_groups=[[[101, 14, 17]], [[102, 0, 2]]],
        ),
        "N38": keep(ranges=[[102, 4, 10]]),
        "N39": keep("Điều trị không mổ trật khớp háng trung tâm", [[103, 6, 13]]),
        "N40": keep("Kéo liên tục trong trật khớp háng trung tâm", [[104, 0, 2]]),
        "N42": keep(ranges=[[102, 4, 12]]),
        "N44": keep(
            "Mổ kết hợp xương ổ cối trong trật háng trung tâm",
            [[103, 6, 7], [103, 13, 15]],
        ),
        "N45": keep("Nắn thử nhẹ nhàng trật háng4–21ngày", [[104, 2, 4]]),
        "N46": keep(ranges=[[104, 2, 6]]),
        "N48": keep("Kéo liên tục trước nắn trật háng4–21ngày", [[104, 2, 4]]),
        "N49": keep(
            "Đục xương dưới mấu chuyển sửa trục chi ở trật háng lâu năm",
            [[104, 2, 3], [104, 5, 6]],
        ),
    }
    s["edges"] = {
        "E2": hold("Cơ chế tai nạn không phải Condition."),
        "E8": keep(ranges=[[99, 14, 19]]),
        "E16": keep(condition="Có vỡ hõm khớp, sứt vỡ chỏm", ranges=[[101, 2, 3]]),
        "E21": keep(
            condition="Trật trung tâm có vỡ hõm khớp, lún sâu; kéo sau khi gây mê đưa chỏm ra và kiểm tra Xquang"
        ),
        "E23": keep(
            condition="Trật háng kèm vỡ chỏm ở người trung niên/người già không lao động nặng",
            ranges=[[102, 1, 2]],
        ),
    }
    for h, target in [
        (9, "N4"),
        (18, "N4"),
        (23, "N4"),
        (24, "N4"),
        (33, "N4"),
        (34, "N4"),
    ]:
        s["held"][f"H{h}"] = merge(target, "Cùng root trật khớp háng trong bài.")
    for h, name in [
        (6, "Động mạch dây chằng tròn"),
        (7, "Động mạch mũ"),
        (8, "Động mạch thân xương đùi"),
    ]:
        s["held"][f"H{h}"] = recover(name, [[98, 7, 8]])
    s["held"]["H16"] = merge(
        "H6", "Cùng động mạch dây chằng tròn ở đoạn mạch nuôi chỏm."
    )
    s["held"]["H17"] = merge("H7", "Cùng động mạch mũ ở đoạn mạch nuôi chỏm.")
    s["held"]["H19"] = recover("Phẫu thuật trật khớp háng độ3 và4", [[100, 6, 12]])
    for h, left, right, rel, rg in [
        (2, "N4", "N7", "HAS_FINDING", [[99, 7, 9]]),
        (3, "N4", "N1", "HAS_FINDING", [[99, 7, 10]]),
        (4, "N4", "N5", "MAY_CAUSE", [[99, 10, 12]]),
        (5, "N4", "N2", "MAY_CAUSE", [[99, 10, 13]]),
        (12, "N4", "N19", "CLASSIFIED_BY", [[99, 21, 23], [100, 0, 6]]),
        (13, "N4", "N16", "CLASSIFIED_BY", [[100, 6, 12]]),
        (14, "N4", "H19", "MANAGED_BY", [[100, 6, 12]]),
        (20, "N4", "N5", "MAY_CAUSE", [[101, 3, 7]]),
        (21, "N4", "N28", "MAY_CAUSE", [[101, 7, 8]]),
        (22, "N4", "N30", "MAY_CAUSE", [[101, 3, 4], [101, 8, 9]]),
        (25, "N4", "N43", "MANAGED_BY", [[101, 10, 14]]),
        (26, "N4", "N37", "MANAGED_BY", [[101, 14, 17], [102, 0, 2]]),
        (27, "N4", "N38", "MANAGED_BY", [[102, 3, 10]]),
        (28, "N4", "N42", "MANAGED_BY", [[102, 10, 13]]),
        (29, "N4", "N34", "MANAGED_BY", [[103, 0, 3]]),
        (30, "N4", "N35", "MANAGED_BY", [[103, 3, 6]]),
        (31, "N4", "N39", "MANAGED_BY", [[103, 6, 13]]),
        (32, "N4", "N44", "MANAGED_BY", [[103, 6, 7], [103, 13, 15]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["held"]["H14"]["condition"] = (
        "Độ3 hoặc4 trong phân độ tại mục4.2; không đồng nhất độ Boehler khác ở102.0"
    )
    s["held"]["H15"] = hold(
        "Gộp điều kiện độ3hoặc4 vào một cạnh có nguồn và scope rõ; Category không làm đầu MANAGED_BY."
    )
    s["held"]["H21"]["condition"] = "Trật háng trung tâm"
    s["held"]["H26"]["condition"] = (
        "Nắn/kéo cấp cứu thất bại hoặc vỡ xương nặng; giữ từng chỉ định trong block nguồn"
    )
    s["held"]["H30"]["condition"] = "Sau nắn; bột3tuần nếu có gãy xương kèm"
    s["held"]["H31"]["condition"] = (
        "Trật háng trung tâm; không lệch/<3mm hoặc các điều kiện không mổ được liệt kê"
    )
    s["held"]["H32"]["condition"] = (
        "Trật trung tâm: ổ cối vỡ nặng, lệch nhiều, bệnh nhân trẻ"
    )
    s["missing"] = [
        {
            "pdf_pages": [101, 103, 104],
            "kind": "distinct_traction_protocols",
            "reason": "Sách ghi kéo4–6tuần,6–8tuần và3tuần ở các đoạn/chỉ định riêng. Không nhập thành một thời gian mặc định.",
        },
        {
            "pdf_pages": [100, 102],
            "kind": "classification_scope",
            "reason": "Phân độ mục4.2 và độ Boehler mục điều trị không được đồng nhất chỉ vì cùng số3/4. Category không trực tiếp làm đầu MANAGED_BY.",
        },
    ]
    return s


def lesson18():
    s, p = base(18, list(range(105, 114)))
    viewed_replacements(
        s,
        p,
        list(range(105, 114)),
        [
            ("gãy cẳng tươi", "gãy cành tươi"),
            ("Gãy cẳng tươi", "Gãy cành tươi"),
            ("gãy hồ", "gãy hở"),
            ("xương hồ", "xương hở"),
            ("sắp-ngửa", "sấp-ngửa"),
            ("chòm", "chỏm"),
            ("mòm", "mỏm"),
        ],
    )
    for key, pairs in {
        "105.0": [("CẮNG", "CẲNG")],
        "105.9": [("chóp quay", "chỏm quay"), ("trăm trụ", "trâm trụ")],
        "105.10": [("bất khớp", "bắt khớp")],
        "106.1": [("Dịch tể", "Dịch tễ")],
        "106.2": [("đúng thứ", "đứng thứ"), ("lỗi cầu", "lồi cầu")],
        "107.8": [("càn tươ", "cành tươi")],
        "107.10": [("sáp tròn", "sấp tròn")],
        "107.16": [("Định nội tuy", "Đinh nội tuỷ")],
        "108.0": [("điện gãy", "diện gãy")],
        "108.1": [("cố ép", "có ép")],
        "108.2": [("sắp ngừa", "sấp ngửa")],
        "108.15": [("Gãy cẳng tay", "Gãy cành tươi")],
        "108.23": [("chính hình", "chỉnh hình")],
        "109.1": [("gãy mê tỉnh", "gây mê tĩnh")],
        "109.2": [("gãy tê", "gây tê")],
        "109.4": [("Người phụ nữ", "Người phụ nắn")],
        "109.5": [("Người đàn ông", "Người nắn")],
        "109.6": [("đầu tách", "đũa tách")],
        "109.13": [("mồm trám", "mỏm trâm"), ("màu trụ", "mào trụ")],
        "110.0": [("Đứng định có chót", "Đóng đinh có chốt")],
        "110.3": [
            ("Mở cắt", "Mổ cắt"),
            ("rách rộng", "rạch rộng"),
            ("tuy độ", "tuỳ độ"),
        ],
        "112.18": [("Theo dõi động mạch", "Đo giao động động mạch")],
        "112.20": [("Doppler máu", "Doppler màu")],
        "112.31": [("nghỉ ngơi", "nghi ngờ")],
        "113.2": [("căng tay", "cẳng tay")],
        "113.15": [("đuôi ngón", "duỗi ngón")],
        "113.18": [("xương xếp", "xương xốp"), ("xương chày", "xương chậu")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": hold("Cơ chế chấn thương không phải ClinicalPrinciple."),
        "N4": hold(
            "Mô tả sinh lý vận động không phải ClinicalPrinciple theo taxonomy hiện tại; giữ ở nội dung bệnh/giải phẫu."
        ),
        "N1": keep(
            "Gãy thân2xương cẳng tay",
            content_groups=[
                [[105, 0, 13], [106, 1, 9]],
                [[107, 0, 18], [108, 0, 27]],
                [[109, 0, 17]],
            ],
        ),
        "N3": keep(
            "Gãy xương hở cẳng tay", content_groups=[[[106, 8, 9]], [[110, 2, 6]]]
        ),
        "N8": keep(
            "Khớp giả sau gãy cẳng tay", [[108, 0, 1], [113, 16, 19]], type="Condition"
        ),
        "N16": keep(
            "Can lệch sau gãy cẳng tay", [[108, 0, 1], [113, 16, 18]], type="Condition"
        ),
        "N15": keep(ranges=[[108, 1, 2], [109, 8, 15]]),
        "N19": keep("Điều trị chỉnh hình gãy di lệch1/3dưới cẳng tay", [[109, 0, 7]]),
        "N23": keep("Phẫu thuật gãy thân2xương cẳng tay", [[109, 7, 17]]),
        "N38": keep(
            "Điều trị bảo tồn khi nghi chèn ép khoang cẳng tay",
            [[112, 29, 33], [113, 0, 3]],
        ),
        "N41": keep(ranges=[[111, 1, 8]]),
        "N44": keep(
            "Hội chứng chèn ép khoang cẳng tay",
            content_groups=[[[110, 6, 13]], [[111, 1, 8], [112, 18, 33], [113, 0, 10]]],
        ),
        "N47": keep(ranges=[[112, 18, 21]]),
        "N50": keep(ranges=[[111, 7, 8], [113, 3, 10]]),
        "N51": keep(ranges=[[113, 13, 16]]),
    }
    for i, target in [
        (2, "N1"),
        (6, "N1"),
        (26, "N1"),
        (22, "N3"),
        (37, "N3"),
        (24, "N15"),
        (21, "N44"),
        (45, "N44"),
        (49, "N50"),
    ]:
        s["nodes"][f"N{i}"] = merge(
            target,
            "Cùng đối tượng trong chương và cùng scope; giữ các block nguồn khác nhau.",
        )
    s["edges"] = {
        "E6": edge("N1", "N16", "MAY_CAUSE", [[108, 0, 1]]),
        "E7": edge("N1", "N8", "MAY_CAUSE", [[108, 0, 1]]),
        "E11": keep(
            condition="Điều trị bảo tồn không kết quả; không phải mọi gãy1/3dưới",
            ranges=[[109, 7, 12]],
        ),
        "E12": keep(
            condition="Gãy cẳng tay có biến chứng chèn ép khoang", ranges=[[109, 7, 12]]
        ),
        "E16": keep(
            condition="Gãy cẳng tay hở, theo mục chỉ định phẫu thuật",
            ranges=[[109, 7, 12]],
        ),
        "E21": keep(
            condition="Xquang để xác định gãy xương kèm; không xác định riêng hội chứng khoang"
        ),
        "E24": keep(
            condition="Gãy hở cẳng tay độ3 đến muộn, nếu không có khung Hoffmann"
        ),
        "E25": keep(
            condition="Sau6giờ không tiến triển thêm, áp lực<30mmHg, cẳng tay mềm, các ngón cử động bình thường"
        ),
        "E27": keep(
            condition="Lâm sàng rõ rệt hoặc áp lực khoang cao>30mmHg; sơ đồ112 xác nhận nhánh lâm sàng rõ mở cân",
            ranges=[[113, 3, 10]],
        ),
    }
    for h, target in [
        (8, "N11"),
        (16, "N1"),
        (25, "N1"),
        (27, "N1"),
        (30, "N1"),
        (36, "N44"),
        (37, "N16"),
        (38, "N8"),
    ]:
        s["held"][f"H{h}"] = merge(
            target, "Cùng thực thể đã đối chiếu vị trí và bệnh cảnh trong chương."
        )
    for h, name, rg in [
        (9, "Xương trụ", [[105, 9, 11]]),
        (10, "Cẳng tay", [[105, 7, 13]]),
        (11, "Khớp quay-trụ trên", [[105, 10, 11]]),
        (12, "Khớp quay-trụ dưới", [[105, 10, 11]]),
        (17, "Trật khớp quay-trụ trên", [[108, 19, 20]]),
        (18, "Trật khớp quay-trụ dưới", [[108, 19, 20]]),
        (26, "Gãy ít di lệch hoặc không di lệch ở cẳng tay", [[108, 23, 27]]),
        (39, "Viêm xương sau gãy cẳng tay", [[113, 16, 20]]),
        (40, "Chậm liền xương cẳng tay", [[113, 16, 19]]),
        (
            41,
            "Bó bột duỗi ngón từng giai đoạn trong hội chứng Wolkmann",
            [[113, 13, 16]],
        ),
        (42, "Phá can, sửa trục và kết hợp xương cẳng tay", [[113, 16, 18]]),
        (
            43,
            "Kết hợp xương và ghép xương xốp tự thân (xương chậu) ở cẳng tay",
            [[113, 16, 19]],
        ),
        (
            44,
            "Nạo viêm, lấy xương chết và kháng sinh toàn thân ở cẳng tay",
            [[113, 16, 20]],
        ),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, left, right, rel, rg in [
        (0, "N1", "N11", "LOCATED_IN", [[105, 3, 4]]),
        (1, "N1", "H9", "LOCATED_IN", [[105, 3, 4], [105, 9, 11]]),
        (13, "N1", "N12", "EVALUATED_BY", [[108, 7, 8], [108, 19, 22]]),
        (19, "N5", "H26", "HAS_CATEGORY", [[107, 7, 12], [108, 23, 27]]),
        (20, "N1", "N27", "MANAGED_BY", [[108, 24, 27]]),
        (21, "N1", "N32", "MANAGED_BY", [[108, 24, 27]]),
        (22, "N1", "N15", "MANAGED_BY", [[109, 7, 15]]),
        (23, "N1", "N31", "MANAGED_BY", [[109, 7, 16]]),
        (24, "N1", "N28", "MANAGED_BY", [[109, 7, 17]]),
        (28, "N3", "N1", "IS_A", [[110, 2, 6]]),
        (29, "N1", "N44", "MAY_CAUSE", [[109, 10, 11], [110, 6, 7]]),
        (31, "N44", "N51", "MAY_CAUSE", [[113, 13, 16]]),
        (32, "N51", "H41", "MANAGED_BY", [[113, 13, 16]]),
        (33, "N16", "H42", "MANAGED_BY", [[113, 16, 18]]),
        (34, "N8", "H43", "MANAGED_BY", [[113, 16, 19]]),
        (35, "H39", "H44", "MANAGED_BY", [[113, 16, 20]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    for h in [20, 21]:
        s["held"][f"H{h}"]["condition"] = (
            "Gãy ít hoặc không di lệch; thời gian bột khác nhau trẻ em/người lớn"
        )
    s["missing"] = [
        {
            "pdf_pages": [112],
            "kind": "flowchart",
            "reason": "Đã xem sơ đồ18.10b: lâm sàng rõ hoặc áp lực>30 dẫn mở cân, nhánh<30 theo dõi. Không biến câu chữ có dấu chấm phẩy thành yêu cầu phải đồng thời cả hai.",
        },
        {
            "pdf_pages": [108, 113],
            "kind": "anatomic_part_not_is_a",
            "reason": "Không nhập IS_A xương/khớp với vùng cẳng tay; chấn thương đi kèm cần tránh bỏ sót không đồng nghĩa quan hệ gây ra.",
        },
    ]
    return s


def lesson19():
    s, p = base(19, list(range(114, 123)))
    s["printed_marker_restorations"] = [
        "117.13"
    ]  # PDF: bàn tay khỉ, not temporal marker khi.
    viewed_replacements(
        s,
        p,
        list(range(114, 123)),
        [
            ("gân đuôi", "gân duỗi"),
            ("gấp đuôi", "gấp duỗi"),
            ("không đuôi", "không duỗi"),
            ("nếu đuôi", "nếu duỗi"),
            ("cắt cut", "cắt cụt"),
            ("Cắt cut", "Cắt cụt"),
            ("mềm cut", "mỏm cụt"),
            ("Mềm cut", "Mỏm cụt"),
            ("liệu cao", "liều cao"),
        ],
    )
    for key, pairs in {
        "114.2": [("hay gãy", "hay gặp")],
        "114.8": [("gần giáp", "gân gấp"), ("viêm tẩy", "viêm tấy")],
        "114.13": [("gân giáp", "gân gấp")],
        "114.17": [("chặt hẹp", "chật hẹp")],
        "115.6": [("chuyển vật", "chuyển vạt")],
        "116.6": [("hoạt tử", "hoại tử")],
        "117.4": [("Gân đuôi", "Gân duỗi")],
        "117.12": [("vượt trụ", "vuốt trụ")],
        "117.13": [("bàn tay khi", "bàn tay khỉ")],
        "118.3": [("co giãn", "co ngắn")],
        "119.6": [("thận lợi", "thuận lợi"), ("tim và nội gan", "tìm và nối gân")],
        "119.12": [("vật da", "vạt da"), ("bất chéo", "bắt chéo")],
        "119.13": [("góc móng", "gốc móng")],
        "119.15": [("Vật da", "Vạt da")],
        "120.0": [("rách da", "rạch da"), ("vết da", "vạt da")],
        "121.4": [("khuỷu", "khuy")],
        "121.6": [("nối khâu trọn tru", "mối khâu trơn tru")],
        "121.13": [("bất buộc", "bắt buộc")],
        "122.2": [("đập nát", "dập nát")],
        "122.16": [("hay gãy", "hay gặp"), ("chặt hẹp", "chật hẹp")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N4": keep(
            content_groups=[
                [[114, 0, 19]],
                [[115, 1, 10], [116, 1, 11]],
                [[117, 0, 15], [118, 1, 16]],
                [[122, 15, 18]],
            ]
        ),
        "N14": keep("Đứt gân duỗi ngón tay", [[117, 4, 7]]),
        "N17": keep(ranges=[[119, 0, 1]]),
        "N20": keep("Các ngón tay co ngắn lại", [[118, 1, 4]]),
        "N33": keep("Vuốt trụ, mất cảm giác ngón5 và một phần ngón4", [[117, 11, 13]]),
        "N35": keep(ranges=[[120, 1, 4]]),
        "N41": keep(
            "Khâu gân theo kỹ thuật Kessler", [[121, 0, 12]], type="Intervention"
        ),
        "N43": keep(ranges=[[121, 0, 11]]),
        "N44": keep(ranges=[[122, 0, 4]]),
        "N45": keep("Tổn thương gân bàn tay", [[117, 0, 7], [121, 0, 11]]),
        "N48": keep(ranges=[[122, 8, 12]]),
        "N53": hold(
            "Nguồn là bài tập bệnh nhân dưới hướng dẫn của phẫu thuật viên, không xác lập Skill của người học."
        ),
        "N54": keep(ranges=[[122, 12, 15]]),
    }
    for i in [36, 37, 40]:
        s["nodes"][f"N{i}"] = hold(
            "Chỉ khâu/vật liệu phẫu thuật không phải Drug. Schema không có Device/Material; không ép type để nối USES_DRUG."
        )
    for i in [12, 52]:
        s["nodes"][f"N{i}"] = merge(
            "N4", "Cùng vết thương bàn tay ở phần khám/kết luận."
        )
    s["nodes"]["N50"] = merge(
        "N0",
        "Cùng phục hồi chức năng sau vết thương bàn tay, giữ nguồn nhấn mạnh và chỉ dẫn riêng.",
    )
    s["edges"] = {
        "E18": hold(
            "Kessler là kỹ thuật khâu cụ thể, không phải ClinicalPrinciple. Không đổi quan hệ thành IS_A không có đề xuất nguồn tương ứng."
        ),
        "E0": keep(
            condition="Vết thương lớn, mất da nhiều, gân xương không được che phủ"
        ),
        "E2": keep(ranges=[[114, 11, 16]]),
    }
    s["held"]["H0"] = recover(
        "Thăm khám lâm sàng vết thương bàn tay", [[115, 1, 7]], kind="practical"
    )
    for h, name, rg in [
        (6, "Gân bàn tay", [[114, 3, 4], [115, 7, 10]]),
        (7, "Xương bàn tay", [[115, 6, 7], [118, 1, 8]]),
        (8, "Gân gấp nông ngón tay", [[115, 8, 10]]),
        (9, "Gân gấp sâu ngón tay", [[115, 8, 10]]),
        (24, "Thần kinh quay chi phối bàn tay", [[117, 11, 12], [117, 14, 15]]),
        (
            25,
            "Bàn tay rũ và rối loạn vận động cảm giác do tổn thương thần kinh quay",
            [[117, 14, 15]],
        ),
        (28, "Feldene", [[119, 0, 1]]),
        (29, "Morphine", [[119, 0, 1]]),
        (30, "Amitaze", [[119, 1, 2]]),
        (31, "a chymotrypsin", [[119, 1, 2]]),
        (39, "Kháng sinh liều cao toàn thân sau mổ bàn tay", [[122, 6, 8]]),
        (45, "Điều trị sau mổ vết thương bàn tay", [[122, 6, 15]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h in [26, 27, 37, 38, 44]:
        s["held"][f"H{h}"] = merge(
            "N4", "Cùng root trong chương, không tạo thêm node tiêu đề."
        )
    for h, left, right, rel, rg in [
        (3, "H0", "N4", "APPLIES_TO", [[115, 1, 7]]),
        (4, "H8", "N11", "IS_A", [[115, 9, 10]]),
        (5, "H9", "N11", "IS_A", [[115, 9, 10]]),
        (10, "N4", "N33", "HAS_FINDING", [[117, 11, 13]]),
        (11, "N4", "N22", "HAS_FINDING", [[117, 13, 14]]),
        (12, "N4", "H25", "HAS_FINDING", [[117, 14, 15]]),
        (13, "N18", "N29", "HAS_FINDING", [[118, 6, 7]]),
        (14, "N4", "N19", "MANAGED_BY", [[118, 9, 12]]),
        (15, "N4", "N23", "MANAGED_BY", [[118, 9, 10], [118, 12, 13]]),
        (16, "N4", "N26", "MANAGED_BY", [[118, 9, 10], [118, 13, 14]]),
        (17, "N4", "N28", "MANAGED_BY", [[118, 9, 10], [118, 15, 16]]),
        (18, "N4", "N17", "MANAGED_BY", [[119, 0, 1]]),
        (19, "N4", "N27", "MANAGED_BY", [[119, 1, 2]]),
        (20, "N17", "H28", "USES_DRUG", [[119, 0, 1]]),
        (21, "N17", "H29", "USES_DRUG", [[119, 0, 1]]),
        (22, "N27", "H30", "USES_DRUG", [[119, 1, 2]]),
        (23, "N27", "H31", "USES_DRUG", [[119, 1, 2]]),
        (32, "N4", "N38", "MANAGED_BY", [[119, 3, 8]]),
        (33, "N4", "N46", "MANAGED_BY", [[119, 8, 14]]),
        (34, "N34", "N35", "MANAGED_BY", [[120, 1, 4]]),
        (35, "N4", "H39", "MANAGED_BY", [[122, 6, 8]]),
        (36, "N4", "N42", "MANAGED_BY", [[122, 6, 12]]),
        (40, "N4", "H45", "MANAGED_BY", [[122, 6, 15]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    for h, condition in [
        (10, "Khi tổn thương thần kinh trụ"),
        (11, "Khi tổn thương thần kinh giữa"),
        (12, "Khi tổn thương thần kinh quay"),
        (13, "Di chứng về sau"),
    ]:
        s["held"][f"H{h}"]["condition"] = condition
    s["held"]["H41"] = hold(
        "Bài tập là thành phần điều trị sau mổ, không phải IS_A giữa hai can thiệp."
    )
    for h in [42, 43]:
        s["held"][f"H{h}"] = hold(
            "Nguồn nói PHCN để TRÁNH di chứng; không phải PHCN gây dính gân/cứng khớp. Không có quan hệ PREVENTS trong schema."
        )
    s["missing"] = [
        {
            "pdf_pages": [121],
            "kind": "unsupported_material_type",
            "reason": "Chỉ thép/Prolen/chỉ10/0 giữ trong quote kỹ thuật, không nhập thành Drug.",
        },
        {
            "pdf_pages": [121],
            "kind": "figure_caption_scope",
            "reason": "Đã xem hình19.8: trong hình có chữ Tajima và caption Kessler. Giữ đúng từng chữ in, không tự định danh kỹ thuật từ hình.",
        },
        {
            "pdf_pages": [122],
            "kind": "printed_posture",
            "reason": "Cổ tay GẤP20–30độ giữ nguyên bản in; không đổi thành duỗi theo kiến thức ngoài.",
        },
    ]
    return s


def lesson20():
    s, p = base(20, list(range(123, 130)))
    viewed_replacements(
        s,
        p,
        list(range(123, 130)),
        [
            ("thất lưng", "thắt lưng"),
            ("thất lùng", "thắt lưng"),
            ("ngược", "ngực"),
            ("mềm nha", "mỏm nha"),
            ("mềm khớp", "mỏm khớp"),
            ("mềm gai", "mỏm gai"),
            ("mồm gai", "mỏm gai"),
            ("mồm khớp", "mỏm khớp"),
            ("tuy", "tuỷ"),
            ("tụy", "tuỷ"),
            ("bí đại", "bí đái"),
            ("Bí đại", "Bí đái"),
            ("đi đại", "đi đái"),
            ("tự đại", "tự đái"),
            ("dẫn dẫn", "dần dần"),
            ("vũng", "vững"),
        ],
    )
    for key, pairs in {
        "123.2": [("sự đất", "sụt đất")],
        "123.4": [
            ("bó cố bột", "có bột"),
            ("cố bột", "có bột"),
            ("và dây tập", "và dậy tập"),
        ],
        "123.5": [("cứu vẫn", "cứu vãn")],
        "124.1": [("phần xạ", "phản xạ"), ("cơ thất", "cơ thắt"), ("đa bìu", "da bìu")],
        "124.6": [("phần xạ", "phản xạ")],
        "124.13": [("Bông đai", "Bóng đai")],
        "124.14": [("bơi trước", "bơi trườn")],
        "124.16": [("ngờ gây", "ngờ gãy")],
        "124.22": [("mở sớm", "mổ sớm")],
        "125.0": [("CHẤM-CỐ", "CHẨM-CỔ")],
        "125.1": [("chấm cố", "chẩm cổ")],
        "125.2": [("chấm C1", "chẩm C1")],
        "125.10": [("MỒM", "MỎM")],
        "125.21": [("Bắn", "Bắt")],
        "125.23": [("MỒM", "MỎM"), ("ĐÓT", "ĐỐT")],
        "126.1": [("gây trật", "gãy trật")],
        "126.7": [("nẹp phía", "néo phía")],
        "126.9": [("GÂY", "GÃY")],
        "126.10": [("Gây thân", "Gãy thân")],
        "126.12": [("mảnh gây mổ", "mảnh gãy mỏm"), ("gai nhau", "gài nhau")],
        "126.14": [("Nghiêm pháp", "Nghiệm pháp")],
        "126.15": [("Gây thân", "Gãy thân")],
        "126.17": [("được tủy theo", "được tuỳ theo")],
        "126.18": [
            ("ruồi cổ", "ruỗi cổ"),
            ("càn xương", "cán xương"),
            ("tuyên giáp", "tuyến giáp"),
            ("càn cổ", "cân cổ"),
        ],
        "127.2": [("chính hình", "chỉnh hình")],
        "127.5": [("gãy gãy cẳng chân", "gãy gập căng dãn")],
        "127.9": [("GẤY", "GÃY"), ("NGƯỢC-THẤT LÙNG", "NGỰC-THẮT LƯNG")],
        "127.11": [("Lực gãy", "Lực gập")],
        "127.14": [("lấp áo", "lắp áo")],
        "128.4": [("gây nặng", "gãy nặng"), ("cứu vẫn", "cứu vãn")],
        "128.7": [("gây trật", "gãy trật")],
        "128.10": [("chỗ gây", "chỗ gãy")],
        "128.14": [("sóc", "sốc")],
        "128.16": [("tránh trở", "trăn trở")],
        "128.19": [("để đại", "để đái")],
        "129.1": [("cấp lại xã", "cặp lại xả")],
        "129.5": [("đại đẫm", "đái dầm")],
        "129.6": [("Cơ thất", "Cơ thắt"), ("đại được", "đái được")],
        "129.7": [
            ("Kiểu đại", "Kiểu đái"),
            ("đẫm dễ", "dầm dề"),
            ("kiểu đại", "kiểu đái"),
        ],
        "129.9": [("dễ phòng", "đề phòng")],
        "129.12": [("Sần sóc", "Săn sóc"), ("mồm phân", "móc phân")],
        "129.14": [("GÂY", "GÃY"), ("THẤT", "THẮT")],
        "129.15": [("gây nhiều mạnh", "gãy nhiều mảnh")],
        "129.16": [
            ("gây nhiều mạnh", "gãy nhiều mảnh"),
            ("thể mở", "thể mổ"),
            ("bẻ cao", "bề cao"),
        ],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N6": keep(content_groups=[[[123, 0, 14], [124, 0, 23]], [[129, 10, 12]]]),
        "N2": merge(
            "N58", "Cùng thương tổn đoạn ngực-thắt lưng, phần đại cương và mục8."
        ),
        "N4": keep(content_groups=[[[123, 5, 6]], [[128, 13, 21], [129, 0, 14]]]),
        "N5": keep(
            "Methylprednisolone (bản2006)",
            content_groups=[[[124, 18, 21]], [[126, 0, 2]]],
        ),
        "N7": keep("Cố định bằng có bột cột sống (điều trị trước kia)", [[123, 4, 5]]),
        "N12": keep(ranges=[[124, 5, 8]]),
        "N16": keep("Thương tổn vùng chẩm-cổ", [[125, 0, 10]]),
        "N21": hold(
            "Nguy cơ đe doạ tính mạng là mức ưu tiên ABC, chưa phải một Condition cụ thể."
        ),
        "N25": keep("Liệt tay nhưng chân không liệt hoặc liệt nhẹ", [[125, 4, 7]]),
        "N28": keep("Trật khớp chẩm-C1", [[125, 0, 3]]),
        "N30": keep(ranges=[[125, 3, 10]]),
        "N32": keep("Bắt vít phía trước trong gãy cổ mỏm nha", [[125, 19, 23]]),
        "N34": keep(ranges=[[125, 10, 23]]),
        "N36": keep(ranges=[[126, 0, 4]]),
        "N39": keep("Buộc vòng mỏm gai, néo phía sau", [[126, 4, 9]]),
        "N42": keep(ranges=[[126, 16, 20]]),
        "N43": keep("Gãy cột sống ngực", [[127, 0, 9]]),
        "N46": keep(ranges=[[126, 9, 20]]),
        "N50": keep(ranges=[[126, 3, 9]]),
        "N52": keep(ranges=[[127, 4, 6]]),
        "N54": keep("Mảnh gãy mỏm khớp gài nhau, nắn không vào", [[126, 12, 13]]),
        "N55": keep("Gãy trật mỏm khớp đốt sống cổ", [[125, 23, 26], [126, 0, 9]]),
        "N58": keep("Gãy cột sống đoạn ngực-thắt lưng", [[127, 9, 23], [128, 0, 13]]),
        "N60": keep(ranges=[[128, 2, 13]]),
        "N62": keep("Liệt tuỷ không hoàn toàn sau chấn thương", [[128, 3, 13]]),
        "N63": keep("Gãy ngực-thắt lưng vững", [[127, 11, 17]]),
        "N64": keep("Gãy ngực-thắt lưng không vững", [[127, 17, 23]]),
        "N65": keep(
            "Bó áo bột hay lắp áo nẹp ở gãy ngực-thắt lưng vững", [[127, 12, 15]]
        ),
        "N70": keep(ranges=[[128, 13, 18]]),
        "N73": keep("Bí ỉa sau liệt tuỷ", [[129, 12, 14]], type="Condition"),
        "N78": keep(
            "Bàng quang tự chủ sau tổn thương tuỷ thấp", [[129, 6, 8]], type="Condition"
        ),
        "N81": keep(
            "Đại tiện không tự chủ sau liệt tuỷ", [[129, 12, 14]], type="Condition"
        ),
        "N86": keep("Gãy cột sống thắt lưng thấp", [[129, 14, 17]]),
    }
    for i, target in [
        (14, "N8"),
        (40, "N5"),
        (45, "N15"),
        (51, "N43"),
        (71, "N4"),
        (79, "N6"),
        (80, "N19"),
        (82, "N75"),
    ]:
        s["nodes"][f"N{i}"] = merge(
            target,
            "Cùng thực thể và phạm vi được đối chiếu trong cùng chương; hợp các đoạn nguồn.",
        )
    s["edges"] = {
        "E13": keep(
            condition="Chỉ khi không vững hoặc điều trị bảo tồn thất bại; sách ghi chỉ định ít và chưa rõ ràng"
        ),
        "E26": hold(
            "Giải ép trước là một cách mổ, không phải toàn bộ can thiệp IS_A một thành phần."
        ),
        "E29": hold(
            "Buộc vòng phía sau là một cách mổ, không phải quan hệ IS_A bao hàm ngược."
        ),
        "E33": keep(
            condition="Nắn cấp cứu khi có chỉ định; ngoại lệ không liệt hoặc chỉ liệt rễ ở gãy trật1bên theo126.1",
            ranges=[[126, 0, 4]],
        ),
        "E39": keep(
            condition="Gãy ngực-thắt lưng VỮNG, không liệt thần kinh",
            ranges=[[127, 12, 15]],
        ),
        "E40": keep(
            condition="Gãy ngực-thắt lưng KHÔNG VỮNG",
            ranges=[[127, 17, 23], [128, 0, 2]],
        ),
        "E41": keep(
            condition="Liệt không hoàn toàn do gãy ngực-thắt lưng; các chỉ định cấp cứu trong128.5–10",
            ranges=[[128, 3, 13]],
        ),
        "E42": keep(
            condition="Gãy ngực-thắt lưng vững, không liệt; theo tiến trình Magnus"
        ),
        "E43": keep(condition="Gãy ngực-thắt lưng vững, có người hướng dẫn"),
        "E46": edge(
            "N6",
            "N77",
            "MAY_CAUSE",
            [[129, 5, 6]],
            "Thương tổn tuỷ cao hơn trung tâm Budge",
        ),
        "E47": keep(condition="Gãy nhiều mảnh thắt lưng thấp kèm liệt thần kinh"),
        "E48": keep(condition="Gù hoặc bề cao đốt sống mất trên50%"),
    }
    for h, target in [
        (20, "N60"),
        (21, "N6"),
        (22, "N58"),
        (23, "N6"),
        (32, "N6"),
        (33, "N6"),
        (34, "N6"),
        (44, "N6"),
    ]:
        s["held"][f"H{h}"] = merge(
            target, "Cùng đối tượng trong bài, đối chiếu đúng đoạn cột sống."
        )
    for h, name, rg in [
        (10, "Nghiệm pháp Queckensted (bản in)", [[126, 14, 15]]),
        (11, "Tắc khoang dưới nhện", [[126, 14, 15], [128, 9, 10]]),
        (19, "Phân loại gãy ngực-thắt lưng theo độ vững", [[127, 11, 23]]),
        (24, "Mảnh xương rời chèn vào ống tuỷ ngực-thắt lưng", [[128, 5, 7]]),
        (35, "Bí đái sau liệt tuỷ", [[128, 18, 21]]),
        (36, "Thông đái Nelaton", [[128, 18, 21], [129, 0, 1]]),
        (37, "Đặt ống Fooley", [[128, 18, 21], [129, 1, 3]]),
        (38, "Săn sóc bí đái sau liệt tuỷ", [[128, 18, 21], [129, 0, 4]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, left, right, rel, rg in [
        (0, "N6", "N18", "MANAGED_BY", [[123, 4, 5]]),
        (1, "N6", "N7", "MANAGED_BY", [[123, 4, 5]]),
        (3, "N4", "N19", "MAY_CAUSE", [[123, 5, 6]]),
        (5, "N34", "N27", "MANAGED_BY", [[125, 19, 23]]),
        (6, "N34", "N32", "MANAGED_BY", [[125, 19, 23]]),
        (8, "N46", "H10", "EVALUATED_BY", [[126, 10, 15]]),
        (9, "H11", "H10", "EVALUATED_BY", [[126, 14, 15]]),
        (12, "N58", "H19", "CLASSIFIED_BY", [[127, 11, 23]]),
        (13, "H19", "N63", "HAS_CATEGORY", [[127, 12, 13]]),
        (14, "H19", "N64", "HAS_CATEGORY", [[127, 17, 23]]),
        (15, "N58", "N60", "MANAGED_BY", [[128, 2, 13]]),
        (16, "N58", "N6", "IS_A", [[127, 9, 11]]),
        (17, "N62", "N15", "IS_A", [[128, 3, 5]]),
        (18, "N58", "H24", "HAS_FINDING", [[128, 5, 7]]),
        (25, "N67", "N6", "IS_A", [[128, 5, 8]]),
        (26, "N68", "N69", "HAS_FINDING", [[128, 8, 9]]),
        (27, "N4", "N15", "IS_A", [[128, 13, 16]]),
        (28, "N4", "H35", "HAS_FINDING", [[128, 18, 21]]),
        (29, "N4", "H38", "MANAGED_BY", [[128, 18, 21], [129, 0, 4]]),
        (30, "N4", "H36", "MANAGED_BY", [[128, 18, 21], [129, 0, 1]]),
        (31, "N4", "H37", "MANAGED_BY", [[128, 18, 21], [129, 1, 3]]),
        (41, "N6", "N19", "MAY_CAUSE", [[129, 10, 12]]),
        (42, "N73", "N76", "MANAGED_BY", [[129, 12, 13]]),
        (43, "N81", "N74", "MANAGED_BY", [[129, 13, 14]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["held"]["H0"]["condition"] = (
        "Khi có điều kiện, gãy không liệt hoặc gãy có liệt, nhất là không hoàn toàn; quan điểm bản2006"
    )
    s["held"]["H1"]["condition"] = "Điều trị trước kia khi gãy không liệt tuỷ"
    for h in [5, 6]:
        s["held"][f"H{h}"]["condition"] = (
            "Gãy qua CỔ mỏm nha; không áp dụng mặc định đỉnh/nền"
        )
    s["held"]["H15"]["condition"] = (
        "Gãy ngực-thắt lưng liệt không hoàn toàn và các chỉ định cấp cứu liệt kê"
    )
    s["missing"] = [
        {
            "pdf_pages": [124, 126],
            "kind": "historical_drug_claim",
            "reason": "Bản in ghi Methylprednisolon35mg/kg và câu124.20 thiếu dấu phân câu rõ. Giữ nguyên quote và loại cạnh Condition MANAGED_BY Drug sai schema; không tự đổi35 thành30 hoặc tự thêm can thiệp dùng thuốc.",
        },
        {
            "pdf_pages": [127],
            "kind": "printed_sentence_ambiguity",
            "reason": "Dòng127.2 thật sự in Khi không có khung sườn, và có thể...; giữ đúng, không tự suy đoán phủ định.",
        },
        {
            "pdf_pages": [128, 129],
            "kind": "historical_care",
            "reason": "Lịch thông/rút ống và các nhận định tiên lượng giữ theo sách2006, chưa phải hướng dẫn hiện hành. Không đưa ý kiến phá huỷ Budge thành ClinicalPrinciple.",
        },
    ]
    return s


def lesson21():
    s, p = base(21, list(range(130, 142)))
    viewed_replacements(
        s,
        p,
        list(range(130, 142)),
        [
            ("vừng", "vững"),
            ("phổi hợp", "phối hợp"),
            ("phổ hợp", "phối hợp"),
            ("ổ cổI", "ổ cối"),
            ("ổ cổ", "ổ cối"),
            ("ở cổ", "ổ cối"),
            ("chòm", "chỏm"),
            ("ngôi mu", "ngồi mu"),
            ("GÂY", "GÃY"),
        ],
    )
    for key, pairs in {
        "130.16": [("hờn", "hõm")],
        "131.3": [("tòa tàu", "toa tàu")],
        "131.7": [
            ("gây ph", "gãy ph"),
            ("Gây cánh", "Gãy cánh"),
            ("gây kiểu", "gãy kiểu"),
            ("gây 2", "gãy 2"),
            ("ngời-mu", "ngồi-mu"),
            ("gây cánh", "gãy cánh"),
        ],
        "131.8": [("Gây bửa", "Gãy bửa")],
        "132.9": [("dồn thúc", "đùi thúc")],
        "133.2": [("gây một", "gãy một"), ("gây hoàn", "gãy hoàn")],
        "133.13": [("màu chậu", "mào chậu")],
        "134.4": [("sốt", "sốc")],
        "134.9": [("dốt niệu", "đứt niệu")],
        "134.11": [("sốt", "sốc")],
        "134.12": [("bít", "bịt")],
        "134.13": [("võ", "vỡ")],
        "134.15": [("bít", "bịt")],
        "134.17": [("xương xối", "xương xốp")],
        "135.0": [("Hối sức", "Hồi sức"), ("thát 2", "thắt 2")],
        "135.2": [("Đút", "Đứt"), ("cần đẩy", "cân đáy")],
        "135.3": [("dái", "đái")],
        "135.7": [("phần ứng", "phản ứng"), ("dái", "đái")],
        "135.11": [("tạng rộng", "tạng rỗng")],
        "135.18": [("tạng rộng", "tạng rỗng")],
        "136.1": [
            ("chầm", "chỏm"),
            ("xương dài", "xương đùi"),
            ("hông khoa", "hông khoeo"),
        ],
        "136.2": [("gây Malgaigne", "gãy Malgaigne")],
        "136.4": [("thät", "thắt")],
        "136.7": [("đờn", "đơn")],
        "136.10": [("ngán chi", "ngắn chi")],
        "137.7": [("gây", "gãy")],
        "137.8": [("chính hình", "chỉnh hình")],
        "137.10": [("lối cầu dài", "lồi cầu đùi")],
        "137.13": [("gây", "gãy")],
        "137.14": [("gây", "gãy")],
        "137.15": [("Bất vít", "Bắt vít")],
        "137.16": [("bọc lộ", "bộc lộ"), ("vít bất", "vít bắt")],
        "138.1": [("VỖ Ố CỔI", "VỠ Ổ CỐI")],
        "138.11": [("kiểu bẹt", "kiểu bịt"), ("xương dài", "xương đùi")],
        "139.0": [("4/4 chân", "4/4 chậu"), ("bít", "bịt")],
        "139.1": [("xương dùi", "xương đùi")],
        "139.7": [("canh thiệp", "can thiệp")],
        "139.9": [("gai ngôi", "gai ngồi")],
        "139.15": [("xương dùi", "xương đùi")],
        "140.7": [("chính hình", "chỉnh hình")],
        "140.8": [
            ("chính hình", "chỉnh hình"),
            ("lối cầu dùi", "lồi cầu đùi"),
            ("lối cầu củ", "lồi củ"),
            ("xương chậu", "xương chày"),
            ("máu chuyển", "mấu chuyển"),
        ],
        "140.11": [("tri hoãn", "trì hoãn")],
        "141.0": [("Bắn vít", "Bắt vít")],
        "141.3": [("ĐI CHỨNG", "DI CHỨNG"), ("VỖ", "VỠ")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N1": keep(
            content_groups=[
                [[130, 0, 17], [131, 1, 10], [132, 4, 11]],
                [[133, 1, 19], [134, 0, 19]],
                [[135, 0, 22], [136, 0, 11]],
                [[137, 0, 17]],
            ]
        ),
        "N12": merge("N1", "Cùng root gãy chậu; tách các cạnh ở mụcB sang vỡ ổ cối."),
        "N20": keep("Phân loại Noland theo giải phẫu gãy chậu", [[133, 1, 7]]),
        "N21": keep(ranges=[[133, 11, 15]]),
        "N22": keep(ranges=[[133, 15, 18]]),
        "N25": keep(ranges=[[133, 11, 19], [134, 0, 3]]),
        "N28": keep(
            "Mổ dẫn lưu bàng quang và khoang Retzius",
            content_groups=[[[135, 2, 6]], [[135, 6, 11]]],
        ),
        "N33": keep(ranges=[[133, 18, 19], [134, 0, 3]]),
        "N34": keep("Đứt niệu đạo sau do gãy chậu", [[135, 1, 6]]),
        "N36": keep(ranges=[[134, 11, 16]]),
        "N38": keep(
            "Thăm trực tràng, âm đạo tìm tổn thương",
            [[134, 9, 10]],
            type="DiagnosticMethod",
        ),
        "N39": keep("Sốc trong gãy xương chậu", [[134, 4, 5]]),
        "N49": keep(
            "Vỡ ổ cối", [[138, 1, 13], [139, 0, 18], [140, 0, 13], [141, 0, 9]]
        ),
        "N50": keep("Ngắn chi sau toác khớp không nắn được", [[136, 9, 11]]),
        "N55": keep(ranges=[[137, 5, 17]]),
        "N71": keep("Gãy chữT ổ cối", [[139, 16, 18]], type="ClassificationCategory"),
        "N74": keep(
            "Gãy phối hợp cả hai cột trụ ổ cối",
            [[140, 0, 2]],
            type="ClassificationCategory",
        ),
    }
    s["nodes"]["N52"] = merge("N10", "Cùng ổ cối, giữ nguồn cấu tạo cột trụ và mụcB.")
    for i in [0, 2, 3]:
        s["nodes"][f"N{i}"] = hold(
            "Đề xuất Category cơ chế chưa có Classification làm cha; cơ chế được giữ đầy đủ trong nội dung bệnh, không tạo nguyên tắc hay cây mới."
        )
    s["edges"] = {
        "E0": hold("Điều trị chung không IS_A một nhánh can thiệp ngoại khoa."),
        "E1": hold("Xương mu là thành phần, không phải IS_A xương chậu."),
        "E7": keep(ranges=[[135, 6, 10]]),
        "E15": edge("N1", "N38", "EVALUATED_BY", [[134, 9, 10]]),
        "E18": keep(
            condition="Hồi sức tích cực1giờ, truyền2lít máu mà huyết áp không lên"
        ),
        "E19": keep(condition="Khi không có sốc"),
        "E22": hold(
            "Thăm khám để phát hiện rách trực tràng/âm đạo, không gây các tổn thương này."
        ),
        "E25": keep(
            condition="Sau khi qua sốc và xử trí tổn thương phối hợp",
            ranges=[[137, 5, 17]],
        ),
        "E29": hold(
            "Toác khớp là tổn thương trong bệnh cảnh, không có nguồn nói nó gây ra gãy chậu."
        ),
        "E33": edge("N49", "N1", "IS_A", [[138, 4, 5]]),
        "E34": hold("Có thể phối hợp với trật háng không đủ chứng cứ nhân quả."),
        "E35": edge("N49", "N67", "HAS_FINDING", [[138, 12, 13]]),
        "E36": edge("N49", "N63", "HAS_FINDING", [[138, 9, 10]]),
        "E37": edge("N49", "N62", "HAS_FINDING", [[138, 10, 11]]),
        "E38": edge("N49", "N58", "EVALUATED_BY", [[139, 1, 2]]),
        "E39": edge("N49", "N68", "EVALUATED_BY", [[139, 0, 1]]),
    }
    for h in [7, 10, 17, 38, 59, 62, 83, 84, 95]:
        s["held"][f"H{h}"] = merge("N1", "Cùng root gãy chậu trong chương.")
    for h, name, rg in [
        (8, "Xương ngồi", [[130, 12, 16]]),
        (9, "Phần xương chậu tạo khung chậu", [[130, 12, 16]]),
        (39, "Thăm trực tràng", [[135, 12, 14]]),
        (40, "Soi trực tràng", [[135, 12, 14]]),
        (41, "Làm hậu môn nhân tạo đại tràng xích-ma", [[135, 12, 15]]),
        (42, "Xử trí vết thương trực tràng do gãy chậu", [[135, 12, 15]]),
        (43, "Thăm âm đạo", [[135, 15, 17]]),
        (44, "Soi âm đạo", [[135, 15, 17]]),
        (45, "Khâu rách âm đạo", [[135, 15, 18]]),
        (
            46,
            "Mổ nội soi chẩn đoán và xử trí tổn thương bụng phối hợp gãy chậu",
            [[135, 18, 22]],
        ),
        (47, "Tổn thương thần kinh hông to do gãy chậu", [[136, 0, 3]]),
        (
            48,
            "Thắt động mạch chậu trong khi chảy máu khó cầm",
            [[135, 0, 1], [136, 3, 6]],
        ),
        (49, "Nằm nghỉ tại giường trong gãy chậu vững", [[137, 5, 8]]),
        (60, "Phân loại vỡ ổ cối theo Judet và Letournel", [[139, 3, 18], [140, 0, 2]]),
        (61, "Phẫu thuật đặt lại ổ cối gãy thành sau", [[139, 5, 8]]),
        (64, "Trật khớp háng ra trước phối hợp gãy thành trước ổ cối", [[139, 12, 14]]),
        (87, "Chống sốc trong vỡ ổ cối", [[140, 4, 6]]),
        (88, "Nắn cấp cứu trật khớp háng phối hợp vỡ ổ cối", [[140, 4, 7]]),
        (89, "Điều trị chỉnh hình vỡ ổ cối", [[140, 7, 10]]),
        (90, "Xuyên kim kéo liên tục trong vỡ ổ cối", [[140, 7, 10]]),
        (91, "Phẫu thuật có trì hoãn vỡ ổ cối", [[140, 10, 13]]),
        (92, "Kết hợp xương ổ cối", [[140, 10, 13], [141, 0, 2]]),
        (
            93,
            "Bắt vít thành sau, nẹp vít cột trụ sau ổ cối",
            [[140, 10, 13], [141, 0, 1]],
        ),
        (94, "Kết hợp xương hai cột trụ ổ cối", [[140, 10, 13], [141, 1, 2]]),
        (96, "Thay khớp háng toàn bộ do di chứng gãy chậu/ổ cối", [[141, 3, 6]]),
        (97, "Thay chỏm do di chứng hoại tử sau gãy chậu/ổ cối", [[141, 3, 6]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    s["held"]["H63"] = merge(
        "H60",
        "Mục2.3 gãy cột trụ trước chỉ là một loại trong Judet/Letournel, không phải Classification riêng.",
    )
    s["held"]["H85"] = merge("N61", "Trật háng là Condition, không phải Finding.")
    s["held"]["H86"] = merge(
        "N49", "OCR vỡ ở cổ thực tế bản in vỡ ổ cối, không phải cổ xương chậu."
    )
    for h, left, right, rel, rg in [
        (12, "N1", "N20", "CLASSIFIED_BY", [[133, 1, 7]]),
        (13, "N1", "N30", "CLASSIFIED_BY", [[133, 7, 11]]),
        (14, "N1", "N25", "CLASSIFIED_BY", [[133, 11, 19]]),
        (15, "N27", "N23", "IS_A", [[135, 1, 11]]),
        (16, "N34", "N23", "IS_A", [[135, 1, 6]]),
        (18, "N1", "N57", "MAY_CAUSE", [[135, 11, 15]]),
        (19, "N57", "H39", "EVALUATED_BY", [[135, 12, 14]]),
        (20, "N57", "H40", "EVALUATED_BY", [[135, 12, 14]]),
        (21, "N57", "H41", "MANAGED_BY", [[135, 12, 15]]),
        (22, "N57", "H42", "MANAGED_BY", [[135, 12, 15]]),
        (23, "N1", "N45", "MAY_CAUSE", [[135, 15, 18]]),
        (24, "N45", "H43", "EVALUATED_BY", [[135, 15, 17]]),
        (25, "N45", "H44", "EVALUATED_BY", [[135, 15, 17]]),
        (26, "N45", "H45", "MANAGED_BY", [[135, 15, 18]]),
        (27, "N1", "N42", "MAY_CAUSE", [[135, 18, 22]]),
        (28, "N42", "H46", "MANAGED_BY", [[135, 18, 22]]),
        (29, "N1", "H47", "MAY_CAUSE", [[136, 0, 3]]),
        (30, "N1", "H48", "MANAGED_BY", [[136, 3, 6]]),
        (31, "N1", "H49", "MANAGED_BY", [[137, 5, 8]]),
        (32, "N1", "N47", "MANAGED_BY", [[137, 9, 10]]),
        (33, "N1", "N48", "MANAGED_BY", [[137, 10, 11]]),
        (34, "N1", "N53", "MANAGED_BY", [[137, 13, 14]]),
        (35, "N1", "N41", "MANAGED_BY", [[137, 14, 15]]),
        (36, "N1", "N56", "MANAGED_BY", [[137, 15, 16]]),
        (37, "N1", "N46", "MANAGED_BY", [[137, 16, 17]]),
        (50, "N49", "H60", "CLASSIFIED_BY", [[139, 3, 5]]),
        (51, "H60", "N66", "HAS_CATEGORY", [[139, 5, 8]]),
        (52, "H60", "N60", "HAS_CATEGORY", [[139, 8, 10]]),
        (53, "N49", "H61", "MANAGED_BY", [[139, 5, 8]]),
        (54, "N49", "H60", "CLASSIFIED_BY", [[139, 3, 5]]),
        (55, "H60", "N65", "HAS_CATEGORY", [[139, 10, 12]]),
        (56, "H60", "N64", "HAS_CATEGORY", [[139, 12, 14]]),
        (57, "H60", "N59", "HAS_CATEGORY", [[139, 14, 16]]),
        (65, "H60", "N71", "HAS_CATEGORY", [[139, 16, 18]]),
        (66, "H60", "N74", "HAS_CATEGORY", [[140, 0, 2]]),
        (67, "N49", "H87", "MANAGED_BY", [[140, 4, 6]]),
        (68, "N49", "H88", "MANAGED_BY", [[140, 4, 7]]),
        (70, "N49", "H89", "MANAGED_BY", [[140, 7, 10]]),
        (71, "N49", "H90", "MANAGED_BY", [[140, 7, 10]]),
        (72, "N49", "H91", "MANAGED_BY", [[140, 10, 13]]),
        (73, "N49", "H92", "MANAGED_BY", [[140, 10, 13]]),
        (74, "N49", "H93", "MANAGED_BY", [[140, 10, 13], [141, 0, 1]]),
        (75, "N49", "H94", "MANAGED_BY", [[140, 10, 13], [141, 1, 2]]),
        (76, "N1", "N70", "MAY_CAUSE", [[141, 3, 5]]),
        (77, "N1", "N69", "MAY_CAUSE", [[141, 3, 6]]),
        (78, "N1", "N72", "MAY_CAUSE", [[141, 3, 7]]),
        (79, "N1", "N73", "MAY_CAUSE", [[141, 3, 9]]),
        (80, "N70", "H96", "MANAGED_BY", [[141, 4, 5]]),
        (81, "N69", "H97", "MANAGED_BY", [[141, 5, 6]]),
        (82, "N69", "H96", "MANAGED_BY", [[141, 5, 6]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    for h, c in {
        30: "Chảy máu sau phúc mạc khó cầm",
        31: "Gãy vững/một phần, vòng chậu bình thường",
        32: "Toác khớp mu/cùng-chậu loạiB",
        33: "LoạiC mất vững dọc và ngang, kéo11–12kg6tuần",
        34: "Gãy không vững di lệch nhiều",
        35: "Toác khớp mu>2,5cm hoặc gãy xương mu phối hợp",
        36: "Toác khớp cùng chậu và di lệch",
        37: "Toác khớp mu và cùng-chậu",
        53: "Gãy thành sau ổ cối",
        67: "Nếu có sốc",
        68: "Khi phối hợp trật khớp háng",
        72: "Có trì hoãn, chờ mổ kéo liên tục và CT",
        73: "Lệch>3mm, kéo nắn không kết quả",
        74: "Gãy thành/cột trụ sau có chỉ định mổ",
        75: "Gãy hai cột trụ có chỉ định mổ",
    }.items():
        s["held"][f"H{h}"]["condition"] = c
    s["missing"] = [
        {
            "pdf_pages": [139],
            "kind": "printed_view",
            "reason": "Bản in139.0 thật sự ghi4/4 chậu và3/4 bịt; giữ4/4, không tự sửa thành3/4.",
        },
        {
            "pdf_pages": [133, 137],
            "kind": "classification_scope",
            "reason": "Giữ riêng Noland, DonaldTrunkey, AO; không gộp theo chữ vững. Cơ chế không có Classification đề xuất hợp lệ nên giữ nội dung ngoài cây.",
        },
    ]
    return s


def lesson22():
    s, p = base(22, list(range(142, 150)))
    viewed_replacements(
        s,
        p,
        list(range(142, 150)),
        [
            ("máu chuyển", "mấu chuyển"),
            ("chòm", "chỏm"),
            ("xương dài", "xương đùi"),
            ("xương dùi", "xương đùi"),
            ("gãy khớp", "gãy khép"),
        ],
    )
    for key, pairs in {
        "142.4": [("nên cổ", "nền cổ")],
        "142.17": [("bề xương", "bè xương")],
        "142.18": [("bề xương", "bè xương"), ("Bề hình", "Bè hình")],
        "143.4": [("khôe", "khoẻ")],
        "143.6": [("ngoài vi", "ngoại vi")],
        "143.15": [("nên cổ", "nền cổ")],
        "144.10": [("dễ đặt", "dè dặt")],
        "145.0": [("gây càng", "gãy càng")],
        "145.9": [("còng - cut", "cùng - cụt")],
        "146.1": [("càng gây", "càng gãy")],
        "146.4": [("háng khớp", "háng khép")],
        "146.8": [("gãy gập", "gãy dạng")],
        "146.16": [("hệ quặt", "hệ quạt")],
        "147.1": [("gãy còi", "gãy cài")],
        "147.5": [("dùi khớp", "đùi khép"), ("mặt gương", "mặt giường")],
        "147.8": [("đo đặc", "đo đạc")],
        "147.11": [("cổ - bị bị", "cổ - bịt bị")],
        "147.14": [("cổ - bị bình", "cổ - bịt bình")],
        "148.4": [("gãy còi", "gãy cài")],
        "148.5": [("nên cổ", "nền cổ")],
        "148.7": [("dụng bệnh", "dựng bệnh")],
        "149.1": [("gây nên", "gãy nền")],
        "149.2": [("Định nẹp", "Đinh nẹp")],
        "149.3": [("Bất", "Bắt"), ("xấp", "xốp")],
        "149.5": [("cường mạch", "cuống mạch")],
        "149.6": [("góc cổ", "gục cổ")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N0": merge(
            "N17", "Nguồn định nghĩa ghi rõ cổ-mấu chuyển tức nền cổ; cùng nhóm vị trí."
        ),
        "N2": keep(ranges=[[144, 13, 19]]),
        "N4": keep(ranges=[[145, 5, 8]]),
        "N9": keep("Can lệch cổ xương đùi", [[146, 4, 5]]),
        "N11": keep(ranges=[[143, 11, 16]]),
        "N13": keep(
            content_groups=[
                [[142, 0, 19], [143, 1, 8]],
                [[144, 1, 22], [145, 0, 11], [146, 0, 7]],
                [[147, 15, 19]],
            ]
        ),
        "N15": keep(ranges=[[145, 5, 7], [145, 9, 10]]),
        "N16": keep(ranges=[[145, 5, 7], [145, 8, 9]]),
        "N19": hold(
            "Gãy dưới chỏm VÀ xuyên cổ là hai loại cùng nằm nội khớp; không tạo category kép thay hai loại vị trí."
        ),
        "N20": keep("Tiêu chỏm sau gãy cổ xương đùi", [[146, 1, 2]]),
        "N21": keep(
            "Gãy dưới chỏm",
            [[144, 2, 4], [145, 2, 3]],
            reason="Tên lấy đúng caption22.5; dòng144.3 in đảo chỏm dưới được giữ nguyên quote, không sửa bản in.",
        ),
        "N22": keep("Gãy cổ xương đùi cài nhau (gãy dạng)", [[146, 8, 17]]),
        "N26": keep(
            "Gãy cổ xương đùi chính danh (gãy khép)", [[146, 17, 18], [147, 0, 15]]
        ),
        "N30": keep("Đinh nẹp một khối trong điều trị gãy cổ xương đùi", [[149, 2, 3]]),
        "N34": keep(
            "Mổ ghép xương có cuống mạch cho khớp giả cổ đùi ở người trẻ", [[149, 5, 6]]
        ),
        "N36": keep(ranges=[[148, 1, 11]]),
        "N39": keep(ranges=[[148, 16, 20], [149, 0, 1]]),
        "N41": keep(ranges=[[148, 11, 20], [149, 0, 7]]),
        "N42": keep("Đục xương dưới mấu chuyển do can lệch cổ đùi", [[149, 6, 7]]),
    }
    for i, target in [(33, "N10"), (35, "N8"), (38, "N20")]:
        s["nodes"][f"N{i}"] = merge(
            target,
            "Cùng biến chứng trong chương; dùng Condition đã được xác lập ở mục sinh lý bệnh, không ép thành Finding.",
        )
    for i in [1, 13]:
        s["edges"][f"E{i}"] = hold(
            "Động mạch là nguồn cấp máu; danh sách nguồn cấp không phải IS_A ngược giữa mạng mạch và một động mạch."
        )
    s["edges"].update(
        {
            "E10": hold(
                "Gãy cổ không được xác định LOCATED_IN chỏm chỉ từ đoạn mô tả bao khớp."
            ),
            "E17": edge("N22", "N28", "HAS_FINDING", [[146, 8, 13]]),
            "E19": edge("N26", "N25", "EVALUATED_BY", [[147, 9, 15]]),
            "E21": edge("N22", "N23", "HAS_FINDING", [[146, 8, 12]]),
            "E22": edge("N22", "N24", "HAS_FINDING", [[146, 8, 14]]),
            "E23": keep(
                condition="CT đánh giá mức độ loãng xương, không thay Xquang chẩn đoán đường gãy"
            ),
            "E24": keep(
                condition="Người trẻ khoẻ có khả năng mang bột; loạiP1/gãy cài/nền cổ; Lucas có chỉ định riêng già yếu"
            ),
            "E25": keep(
                condition="Gãy đến muộn, đặc biệt có tiêu chỏm/khớp giả/thoái hoá"
            ),
            "E31": edge("N13", "N10", "MAY_CAUSE", [[147, 18, 19]]),
            "E32": edge("N13", "N20", "MAY_CAUSE", [[147, 18, 19]]),
            "E36": edge("N13", "N8", "MAY_CAUSE", [[147, 18, 19]]),
            "E35": keep(
                condition="Gãy di lệch hoặc có biến chứng", ranges=[[148, 11, 15]]
            ),
        }
    )
    for i, n, rg, c in [
        (
            26,
            "N30",
            [[148, 11, 16], [149, 2, 3]],
            "Theo mục các phương pháp phẫu thuật",
        ),
        (27, "N34", [[149, 5, 6]], "Khớp giả cổ đùi ở người trẻ"),
        (28, "N29", [[148, 1, 10]], "Ít dùng theo bản2006; theo chỉ định bảo tồn"),
        (29, "N43", [[148, 1, 11]], "Theo chỉ định bảo tồn trong sách"),
        (30, "N32", [[149, 1, 2]], "Gãy nền cổ"),
        (33, "N40", [[148, 1, 9]], "Theo chỉ định bảo tồn"),
        (34, "N42", [[149, 6, 7]], "Can lệch, gục cổ<100độ"),
        (
            37,
            "N39",
            [[148, 16, 20]],
            "Già>60/gãy sát chỏm/tiêu chỏm/khớp giả; thoái hoá thay toàn bộ; đến muộn>3tuần",
        ),
        (
            38,
            "N37",
            [[148, 7, 8]],
            "Quá già yếu, không chịu được phẫu thuật, nhằm cứu sống",
        ),
    ]:
        s["edges"][f"E{i}"] = edge("N13", n, "MANAGED_BY", rg, c)
    s["held"]["H5"] = recover("Loãng xương", [[142, 10, 14], [147, 13, 14]])
    for h, t in [(11, "N13"), (12, "N25"), (13, "H5")]:
        s["held"][f"H{h}"] = merge(
            t, "Cùng bệnh/phương pháp đúng phạm vi trong chương."
        )
    for h, left, right, rel, rg in [
        (2, "H5", "N13", "MAY_CAUSE", [[142, 10, 14]]),
        (6, "N22", "N13", "IS_A", [[146, 8, 9]]),
        (7, "N26", "N13", "IS_A", [[146, 17, 18]]),
        (8, "N22", "N25", "EVALUATED_BY", [[146, 14, 17]]),
        (9, "N26", "N25", "EVALUATED_BY", [[147, 9, 15]]),
        (10, "H5", "N27", "EVALUATED_BY", [[147, 13, 14]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["missing"] = [
        {
            "pdf_pages": [144],
            "kind": "missing_categories",
            "reason": "LLM có Classification Garden nhưng không đề xuất riêngG1–G4; đã bổ sung toàn đoạn mô tả vào node phân loại, chưa tự tạo thêm node. Pauwels thiếu đề xuất, P2 bản in thiếu dấu bất đẳng thức; không suy đoán.",
        },
        {
            "pdf_pages": [144, 145],
            "kind": "printed_word_order",
            "reason": "Dòng144.3 in gãy chỏm dưới, caption145.2 in gãy dưới chỏm. Giữ cả nguồn, tên theo caption.",
        },
    ]
    return s


def lesson23():
    s, p = base(23, list(range(150, 156)))
    viewed_replacements(
        s,
        p,
        list(range(150, 156)),
        [
            ("xương dài", "xương đùi"),
            ("nếp vít", "nẹp vít"),
            ("đỉnh nội", "đinh nội"),
            ("đóng đỉnh", "đóng đinh"),
            ("Dinh", "Đinh"),
            ("dinh", "đinh"),
            ("lỗi cầu", "lồi cầu"),
            ("máu chuyen", "mấu chuyển"),
            ("máu chuyển", "mấu chuyển"),
            ("chày lưng", "chậu lưng"),
        ],
    )
    for key, pairs in {
        "150.0": [("GẤY", "GÃY")],
        "150.4": [("lối cầu", "lồi cầu")],
        "151.1": [
            ("nhân như tiền mĩa", "nhẵn như tiện mía"),
            ("rộng của", "răng cưa"),
            ("chấp đúng", "chắp đúng"),
        ],
        "151.2": [("chéo vật", "chéo vát")],
        "151.3": [("nắn chính", "nắn chỉnh")],
        "151.5": [("cơ móng", "cơ mông"), ("cơ khớp", "cơ khép")],
        "151.7": [
            ("cơ khớp", "cơ khép"),
            ("cơ dùi", "cơ đùi"),
            ("ngắn chỉ", "ngắn chi"),
            ("nắn chính", "nắn chỉnh"),
            ("gãy mê", "gây mê"),
        ],
        "151.9": [
            ("vùng khoẻ", "vùng khoeo"),
            ("nắn chính", "nắn chỉnh"),
            ("gãy nhẹ", "gấp nhẹ"),
        ],
        "151.11": [("ít dễ", "ít để"), ("gãy góc", "gấp góc")],
        "152.10": [
            ("gãy góc", "gấp góc"),
            ("chỗ gãy của đầu", "chỗ gồ của đầu"),
            ("lao xao", "lạo xạo"),
        ],
        "153.4": [("càn tươi", "cành tươi")],
        "153.6": [("éch", "ếch")],
        "153.7": [("Gãy mềm", "Gây mê")],
        "153.11": [("dàn hồi", "đàn hồi")],
        "153.15": [("lồi cầu dài", "lồi cầu đùi"), ("lỗi cũ", "lồi củ")],
        "154.2": [("gây nẹp", "gãy nẹp")],
        "155.1": [("Tác mạch do mổ", "Tắc mạch do mỡ")],
        "155.2": [("sau gây hở", "sau gãy hở")],
        "155.4": [("dẫn lưu máu", "dẫn lưu mủ"), ("để hồ", "để hở")],
        "155.6": [("gây gãy chi", "gây ngắn chi")],
        "155.7": [("khi gãy chi", "khi ngắn chi")],
        "155.11": [("cơ dùi", "cơ đùi")],
        "155.12": [("vừng", "vững")],
        "155.15": [("dẫn lưu máu", "dẫn lưu mủ")],
        "155.17": [("vật cơ", "vạt cơ"), ("vật da", "vạt da")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N6": keep(
            content_groups=[
                [[150, 0, 11], [151, 0, 14]],
                [[152, 0, 16], [153, 0, 23], [154, 0, 3]],
                [[154, 6, 20], [155, 0, 18]],
            ]
        ),
        "N1": keep(
            "Sốc chấn thương sau gãy thân đùi",
            [[150, 5, 6], [152, 9, 10], [154, 9, 13]],
        ),
        "N12": keep("Đường gãy chéo vát hay chéo xoắn", [[151, 2, 3]]),
        "N14": keep("Gãy thân xương đùi ở trẻ em", [[151, 10, 13], [153, 3, 13]]),
        "N19": keep(ranges=[[152, 0, 5]]),
        "N26": keep(ranges=[[153, 13, 23], [154, 0, 3]]),
        "N30": keep("Điều trị gãy thân xương đùi trẻ em", [[153, 3, 13]]),
        "N32": keep("Kết hợp xương đùi bằng nẹp vít", [[154, 0, 3]]),
        "N34": keep("Gãy hở thân xương đùi", [[154, 6, 7], [154, 13, 17]]),
        "N35": keep("Đóng đinh nội tuỷ Kuntscher mở ổ gãy", [[153, 17, 22]]),
        "N41": keep(ranges=[[153, 13, 17]]),
        "N45": keep("Tắc mạch do mỡ sau gãy thân đùi", [[155, 1, 2]]),
        "N51": keep("Can lệch thân xương đùi", [[155, 5, 9]]),
        "N53": keep("Nạo viêm, lấy xương chết, dẫn lưu mủ", [[155, 14, 16]]),
        "N54": keep("Chuyển vạt cơ, vạt da-cân che xương đùi", [[155, 14, 18]]),
    }
    for i, t in [(9, "N6"), (22, "N19"), (23, "N1"), (44, "N1")]:
        s["nodes"][f"N{i}"] = merge(
            t, "Cùng thực thể và phạm vi của chương, giữ các nguồn."
        )
    s["edges"] = {
        "E13": edge("N34", "N6", "IS_A", [[154, 6, 7], [154, 13, 17]]),
        "E33": edge("N14", "N30", "MANAGED_BY", [[153, 3, 13]]),
        "E36": keep(condition="Ngắn chi>2cm hoặc lệch trục>10độ"),
        "E37": keep(condition="Nếu cần che xương"),
        "E19": keep(ranges=[[152, 14, 16], [153, 0, 3]]),
        "E18": keep(
            condition="Tạm thời chuẩn bị mổ hoặc khi không có chỉ định/điều kiện mổ",
            ranges=[[153, 13, 17]],
        ),
    }
    for i, target, rg in [
        (21, "N32", [[153, 13, 18], [154, 0, 3]]),
        (22, "N35", [[153, 17, 22]]),
    ]:
        s["edges"][f"E{i}"] = edge(
            "N6",
            target,
            "MANAGED_BY",
            rg,
            "Gãy thân đùi người lớn; chỉ định theo từng phương pháp",
        )
    for i, target, rg in [
        (24, "N42", [[153, 3, 4], [153, 11, 12]]),
        (27, "N25", [[153, 3, 4], [153, 12, 13]]),
    ]:
        s["edges"][f"E{i}"] = edge(
            "N14", target, "MANAGED_BY", rg, "Phương pháp kết hợp xương trẻ em"
        )
    for h in [3, 15, 17, 18, 22]:
        s["held"][f"H{h}"] = merge("N6", "Cùng root gãy thân đùi trong chương.")
    for h, name, rg in [
        (7, "Nắn chỉnh gãy1/3giữa thân xương đùi", [[151, 6, 8]]),
        (8, "Nắn chỉnh gãy1/3dưới thân xương đùi", [[151, 8, 10]]),
        (
            23,
            "Winquist: gãy nhiều tầng hoặc mảnh rời lớn>50%đường kính",
            [[152, 0, 1], [152, 3, 4]],
        ),
        (
            24,
            "Winquist: gãy nhiều mảnh, đầu gãy di lệch xa nhau",
            [[152, 0, 1], [152, 4, 5]],
        ),
        (26, "Teo cơ đùi, cứng khớp gối sau gãy thân đùi", [[155, 11, 14]]),
    ]:
        s["held"][f"H{h}"] = recover(
            name, rg, **({"kind": "practical"} if h in [7, 8] else {})
        )
    for h, left, right, rel, rg in [
        (0, "N6", "N7", "LOCATED_IN", [[150, 4, 8]]),
        (12, "H7", "N6", "APPLIES_TO", [[151, 6, 8]]),
        (13, "H8", "N6", "APPLIES_TO", [[151, 8, 10]]),
        (14, "N14", "N6", "IS_A", [[151, 10, 13]]),
        (19, "N6", "N19", "CLASSIFIED_BY", [[152, 0, 5]]),
        (20, "N19", "H23", "HAS_CATEGORY", [[152, 3, 4]]),
        (21, "N19", "H24", "HAS_CATEGORY", [[152, 4, 5]]),
        (25, "H26", "N50", "MANAGED_BY", [[155, 11, 14]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    s["held"]["H12"]["condition"] = "Gãy1/3giữa"
    s["held"]["H13"]["condition"] = "Gãy1/3dưới"
    s["missing"] = [
        {
            "pdf_pages": [151],
            "kind": "missing_classification",
            "reason": "Các category đường gãy/vị trí không có Classification đề xuất phù hợp; không nhập IS_A Category→Condition. Winquist có đủ4loại được nối riêng.",
        },
        {
            "pdf_pages": [153],
            "kind": "printed_caution",
            "reason": "Dòng đinh dưới mấu chuyển thật sự in thêm bột để bị cứng khớp gối; giữ đúng sách và đánh dấu cần chuyên gia xem, không tự thêm chữ tránh.",
        },
        {
            "pdf_pages": [155],
            "kind": "model_omission",
            "reason": "Điều trị nhiễm trùng nặng/cắt cụt cứu sống có trong nguồn nhưng không có node can thiệp được LLM đề xuất độc lập; không tạo cạnh mặc định từ điều trị nhiễm trùng nhẹ.",
        },
    ]
    return s


def lesson24():
    s, p = base(24, list(range(156, 163)))
    viewed_replacements(
        s,
        p,
        list(range(156, 163)),
        [
            ("gầy", "gãy"),
            ("Gầy", "Gãy"),
            ("mổ cần", "mở cân"),
            ("căng chân", "cẳng chân"),
            ("căng dẫn", "căng dãn"),
        ],
    )
    for key, pairs in {
        "156.0": [("CẮNG", "CẲNG")],
        "156.2": [("mâm chân", "mâm chày")],
        "156.3": [("gấp gót", "gấp gối")],
        "156.5": [("mào chân", "mào chày")],
        "156.7": [("bó trí", "bố trí")],
        "156.20": [("trong sạch ra", "trong chọc ra")],
        "157.1": [("đập nát", "dập nát")],
        "157.2": [("vật cơ", "vạt cơ"), ("vật da cần", "vạt da cân")],
        "157.3": [("đập nát", "dập nát")],
        "157.6": [("gãy ra", "gây ra")],
        "157.18": [("gãy chi", "ngắn chi")],
        "157.19": [("tổn kém", "tốn kém")],
        "157.21": [("là để", "là dễ")],
        "158.4": [
            ("bong lót", "bong lóc"),
            ("ngâm", "ngầm"),
            ("dập không", "dập phồng"),
            ("phồng nước", "phỏng nước"),
        ],
        "158.7": [
            ("mạch chân", "mạch chày"),
            ("và chân sau", "và chày sau"),
            ("bầm chân có cứng", "bắp chân có căng"),
        ],
        "158.13": [("tuần hoàn máu", "tuần hoàn mao mạch")],
        "159.7": [("bằng chẩn", "bảng chẩn"), ("đập đứt", "dập đứt")],
        "159.32": [("thi tâm", "thì tâm")],
        "160.18": [("gây kín", "gãy kín")],
        "160.19": [("gây xương dài", "gãy xương đùi")],
        "160.20": [("chi gây bầm", "chi gãy bằng")],
        "160.24": [("gây", "gãy")],
        "160.25": [
            ("gây sưng", "gãy vững"),
            ("gây đơn", "gãy đơn"),
            ("rằng lược", "răng lược"),
        ],
        "160.26": [("bột dài - cứng", "bột đùi - cẳng"), ("gót gấp", "gối gấp")],
        "160.30": [("Bất vít", "Bắt vít"), ("soán", "xoắn")],
        "161.0": [("soắn", "xoắn")],
        "161.2": [("cơ chế phù", "cơ che phủ")],
        "161.3": [("Bắn vít", "Bắt vít")],
        "161.11": [("tổn thương da", "tốt da")],
        "162.3": [("Hành", "Hình")],
        "162.5": [("xương vùng", "xương vững")],
        "162.8": [("Hành", "Hình"), ("rách cân", "rạch cân")],
    }.items():
        patch(s, p, key, *pairs)
    s["printed_marker_restorations"] = ["158.4"]  # PDF phồng, not negation không.
    s["nodes"] = {
        "N0": hold("Cơ chế không phải ClinicalPrinciple."),
        "N5": hold("Cơ chế không phải ClinicalPrinciple."),
        "N1": keep(content_groups=[[[156, 0, 22], [157, 0, 28]], [[158, 0, 15]]]),
        "N6": keep(
            "Gãy hở thân xương cẳng chân",
            [[156, 10, 11], [156, 18, 22], [157, 0, 4], [161, 8, 12], [162, 0, 2]],
        ),
        "N9": keep(
            "Hội chứng chèn ép khoang cẳng chân",
            content_groups=[
                [[156, 8, 9], [157, 4, 12]],
                [[158, 8, 15], [159, 0, 8], [159, 31, 36]],
                [[162, 4, 7]],
            ],
        ),
        "N13": hold(
            "Tổn thương xương gồm đơn giản/phức tạp là tiêu đề gộp, không phải một Category có cha đã được đề xuất."
        ),
        "N16": hold(
            "Di chứng là mục trình bày chứa nhiều bệnh, không phải Condition độc lập."
        ),
        "N19": keep("Can lệch cẳng chân", [[157, 18, 19]]),
        "N29": keep(ranges=[[158, 0, 2]]),
        "N32": keep(ranges=[[160, 18, 23]]),
        "N33": keep(ranges=[[159, 31, 33]]),
        "N37": keep(
            "Mở cân cấp cứu chèn ép khoang cẳng chân", [[159, 31, 33], [162, 4, 7]]
        ),
        "N38": keep("Đóng đinh nội tuỷ kín không chốt cẳng chân", [[161, 6, 8]]),
        "N42": keep("Đóng đinh nội tuỷ có chốt ngang cẳng chân", [[161, 6, 8]]),
        "N43": keep(ranges=[[160, 23, 28]]),
        "N44": keep(
            "Điều trị gãy kín thân xương cẳng chân", [[160, 18, 31], [161, 0, 8]]
        ),
        "N47": keep("Xử trí tốt da và phần mềm trong gãy hở cẳng chân", [[161, 8, 12]]),
    }
    for i, t in [
        (14, "N1"),
        (21, "N9"),
        (24, "N9"),
        (28, "N9"),
        (46, "N9"),
        (23, "N17"),
        (45, "N6"),
        (51, "N37"),
    ]:
        s["nodes"][f"N{i}"] = merge(
            t,
            "Cùng thực thể trong cùng bài và vị trí cẳng chân; hợp nguồn, giữ riêng với cẳng tay.",
        )
    # Registry identities already confirmed; append this chapter's source blocks.
    for i, cid, grade in [
        (2, "MC_d3d42831dee943f79b3083e44ee4850b", "3b"),
        (3, "MC_72f1e6d2069148dc8a79dca0cd9cc8d1", "3c"),
        (7, "MC_9312bc84a5944df68498a5feba6f6551", "3"),
        (8, "MC_7148dc6b07054c43b48206a422d47be2", "2"),
        (10, "MC_f903181961b044e68e303375f476538e", "1"),
        (12, "MC_1fcc25417c6c4b829f1a9f39ce1f7077", "3a"),
    ]:
        s["nodes"][f"N{i}"] = keep(
            f"Gãy xương hở — Phân độ Gustilo — Độ {grade}", canonical_id=cid
        )
    s["edges"] = {
        "E5": keep(ranges=[[157, 20, 22], [158, 0, 2]]),
        "E9": hold(
            "Lâm sàng không rõ phải đo áp lực, không phải mở cân ngay. Chỉ mở khi áp lực>30 hoặc sau theo dõi lâm sàng rõ."
        ),
        "E11": hold(
            "Điều trị gãy kín gồm cấp cứu; không phải IS_A ngược giữa can thiệp chung và một bước."
        ),
    }
    for h, t in [
        (13, "N6"),
        (26, "N11"),
        (43, "N20"),
        (46, "N9"),
        (52, "N33"),
        (56, "N37"),
        (80, "N1"),
        (89, "N1"),
    ]:
        s["held"][f"H{h}"] = merge(t, "Cùng bệnh/phương pháp đúng scope của chương.")
    s["held"]["H14"] = recover(
        "Phân độ gãy xương hở theo Gustilo",
        [[156, 19, 22], [157, 0, 4]],
        canonical_id="MC_bad6dfb5263c4aa18bde65efbebc79bc",
    )
    for h, name, rg in [
        (27, "Hoại thư sau gãy cẳng chân", [[157, 12, 14]]),
        (28, "Hoại thư sinh hơi sau gãy cẳng chân", [[157, 12, 14]]),
        (44, "Hoại tử da sau gãy cẳng chân", [[158, 4, 7]]),
        (45, "Lộ xương thứ phát sau gãy cẳng chân", [[158, 4, 7]]),
        (47, "Đau quá mức dù đã bất động cẳng chân", [[159, 1, 3]]),
        (48, "Căng cứng toàn bộ cẳng chân", [[159, 1, 2], [159, 3, 4]]),
        (49, "Tê bì và kiến bò ở đầu ngón chân", [[159, 1, 2], [159, 4, 5]]),
        (
            50,
            "Đau tăng khi vận động thụ động, căng dãn cơ cẳng chân",
            [[159, 1, 2], [159, 5, 6]],
        ),
        (51, "Liệt vận động các ngón chân", [[159, 1, 2], [159, 6, 7]]),
        (53, "Đo giao động mạch bằng Doppler", [[159, 33, 34]]),
        (54, "Chụp mạch và CTScanner trong chèn ép khoang cẳng chân", [[159, 34, 35]]),
        (55, "Xét nghiệm máu trong chèn ép khoang cẳng chân", [[159, 35, 36]]),
        (81, "Bất động chi gãy cẳng chân bằng nẹp", [[160, 19, 21]]),
        (82, "Phòng chống sốc trong gãy cẳng chân", [[160, 19, 22]]),
        (83, "Giảm đau trong gãy cẳng chân", [[160, 19, 20], [160, 22, 23]]),
        (84, "Morphin", [[160, 22, 23]]),
        (85, "Feldene", [[160, 22, 23]]),
        (86, "Bó bột gãy cẳng chân không di lệch", [[160, 23, 25]]),
        (87, "Nắn kéo và bó bột cẳng chân", [[160, 23, 27]]),
        (88, "Kéo liên tục gãy cẳng chân", [[160, 27, 28]]),
        (92, "Bắt vít đơn thuần gãy chéo vát, xoắn cẳng chân", [[160, 29, 31]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, left, right, rel, rg in [
        (5, "N6", "H14", "CLASSIFIED_BY", [[156, 19, 22]]),
        (6, "H14", "N10", "HAS_CATEGORY", [[156, 20, 21]]),
        (7, "H14", "N8", "HAS_CATEGORY", [[156, 21, 22]]),
        (8, "H14", "N7", "HAS_CATEGORY", [[157, 0, 1]]),
        (9, "N12", "N7", "IS_A", [[157, 0, 2]]),
        (10, "N2", "N7", "IS_A", [[157, 0, 1], [157, 2, 3]]),
        (11, "N3", "N7", "IS_A", [[157, 0, 1], [157, 3, 4]]),
        (15, "N1", "N20", "MAY_CAUSE", [[157, 7, 10]]),
        (16, "N1", "N17", "MAY_CAUSE", [[157, 7, 11]]),
        (17, "N1", "N9", "MAY_CAUSE", [[157, 7, 12]]),
        (18, "N1", "N25", "MAY_CAUSE", [[157, 12, 14]]),
        (19, "H27", "N25", "IS_A", [[157, 12, 14]]),
        (20, "H28", "N25", "IS_A", [[157, 12, 14]]),
        (21, "N1", "N22", "MAY_CAUSE", [[157, 12, 15]]),
        (22, "N1", "N18", "MAY_CAUSE", [[157, 15, 17]]),
        (23, "N1", "N26", "MAY_CAUSE", [[157, 15, 18]]),
        (24, "N1", "N19", "MAY_CAUSE", [[157, 15, 19]]),
        (25, "N1", "N15", "MAY_CAUSE", [[157, 15, 20]]),
        (29, "N1", "N20", "MAY_CAUSE", [[157, 23, 24]]),
        (30, "N1", "H44", "MAY_CAUSE", [[158, 6, 7]]),
        (31, "N1", "H45", "MAY_CAUSE", [[158, 6, 7]]),
        (32, "N9", "N27", "HAS_FINDING", [[158, 12, 15]]),
        (33, "N9", "H47", "HAS_FINDING", [[159, 1, 3]]),
        (34, "N9", "H48", "HAS_FINDING", [[159, 1, 2], [159, 3, 4]]),
        (35, "N9", "H49", "HAS_FINDING", [[159, 1, 2], [159, 4, 5]]),
        (36, "N9", "H50", "HAS_FINDING", [[159, 1, 2], [159, 5, 6]]),
        (37, "N9", "H51", "HAS_FINDING", [[159, 1, 2], [159, 6, 7]]),
        (38, "N9", "N33", "EVALUATED_BY", [[159, 31, 33]]),
        (39, "N9", "H53", "EVALUATED_BY", [[159, 33, 34]]),
        (40, "N9", "H54", "EVALUATED_BY", [[159, 34, 35]]),
        (41, "N9", "H55", "EVALUATED_BY", [[159, 35, 36]]),
        (42, "N9", "N37", "MANAGED_BY", [[159, 31, 33]]),
        (57, "N9", "N37", "MANAGED_BY", [[159, 31, 33]]),
        (58, "N9", "N40", "EVALUATED_BY", [[159, 31, 33], [160, 10, 11]]),
        (59, "N9", "N37", "MANAGED_BY", [[159, 31, 33]]),
        (60, "N9", "N37", "MANAGED_BY", [[159, 0, 8], [159, 31, 33]]),
        (61, "N1", "N44", "MANAGED_BY", [[160, 18, 31], [161, 0, 8]]),
        (62, "N1", "N43", "MANAGED_BY", [[160, 23, 28]]),
        (63, "N1", "H81", "MANAGED_BY", [[160, 19, 21]]),
        (64, "N1", "H82", "MANAGED_BY", [[160, 19, 22]]),
        (65, "N1", "H83", "MANAGED_BY", [[160, 22, 23]]),
        (66, "H83", "H84", "USES_DRUG", [[160, 22, 23]]),
        (67, "H83", "H85", "USES_DRUG", [[160, 22, 23]]),
        (68, "N1", "H86", "MANAGED_BY", [[160, 24, 25]]),
        (69, "N1", "H87", "MANAGED_BY", [[160, 25, 27]]),
        (70, "N1", "H88", "MANAGED_BY", [[160, 27, 28]]),
        (74, "N1", "H92", "MANAGED_BY", [[160, 29, 31]]),
        (76, "N1", "N31", "MANAGED_BY", [[161, 1, 2]]),
        (77, "N1", "N34", "MANAGED_BY", [[161, 2, 3]]),
        (78, "N1", "N38", "MANAGED_BY", [[161, 6, 8]]),
        (79, "N1", "N42", "MANAGED_BY", [[161, 6, 8]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    for h, c in {
        42: "Áp lực>30mmHg",
        57: "Áp lực>30mmHg",
        58: "Áp lực<30mmHg, lâm sàng chưa rõ; nhánh theo dõi hình24.2 đã xem",
        59: "Theo dõi thấy áp lực>30mmHg",
        60: "Theo dõi thấy triệu chứng lâm sàng rõ",
        61: "Gãy kín",
        62: "Không di lệch/di lệch ít và vững; các điều kiện riêng trong source",
        68: "Không di lệch",
        69: "Di lệch ít và gãy vững",
        70: "Không nắn hoàn chỉnh ngay hoặc một số gãy vụn",
        74: "Gãy kín chéo vát/xoắn",
        76: "Gãy kín",
        77: "Gãy kín",
        78: "Gãy kín, không mở ổ",
        79: "Gãy kín, không mở ổ",
    }.items():
        s["held"][f"H{h}"]["condition"] = c
    s["missing"] = [
        {
            "pdf_pages": [159, 160],
            "kind": "flowchart_and_table",
            "reason": "Đã xem bảng Matsen và hình24.2. Không rõ lâm sàng là nhánh đo áp lực, không mở cân ngay; bảng dấu+/− chỉ giữ ở nguồn, chưa dựng thêm quan hệ.",
        },
        {
            "pdf_pages": [156, 157],
            "kind": "canonical_scope",
            "reason": "Gustilo dùng lại7ID đã xác nhận; nguồn IIIc của bài24 gồm thần kinh khác cách diễn đạt bài3, giữ hai block riêng, không tự hợp thành một định nghĩa mới.",
        },
        {
            "pdf_pages": [161],
            "kind": "obsolete_method",
            "reason": "Buộc vòng được sách ghi không còn áp dụng; giữ node có phủ định trong nội dung, không phục hồi cạnh điều trị tích cực.",
        },
    ]
    return s


def lesson25():
    s, p = base(25, list(range(163, 169)))
    viewed_replacements(
        s,
        p,
        list(range(163, 169)),
        [
            ("căng dẫn", "căng dãn"),
            ("đau chới", "đau chói"),
            ("mất cá", "mắt cá"),
            ("Mất cá", "Mắt cá"),
            ("chạy sên", "chày sên"),
            ("gông mộng", "gọng mộng"),
            ("chày tác", "chày mác"),
            ("xương tác", "xương mác"),
            ("sên tác", "sên mác"),
            ("Bất vít", "Bắt vít"),
            ("bất vít", "bắt vít"),
            ("Volkman", "Volkmann"),
        ],
    )
    for key, pairs in {
        "163.9": [("ngồi cùng", "ngồi chùng"), ("ca sơ thấy", "ca sờ thấy")],
        "163.14": [("căng bàn", "cẳng bàn")],
        "163.15": [("giấy da", "giày da"), ("gây nạng", "gậy nạng")],
        "163.16": [
            ("giấy vải", "giày vải"),
            ("giấy da", "giày da"),
            ("giấy nẹp chính", "giày nẹp chỉnh"),
        ],
        "164.5": [("gành nước", "gánh nước")],
        "164.6": [("bóng chuyên", "bóng chuyền")],
        "164.8": [("đặt thẳng", "đạp thẳng")],
        "164.15": [("để hỗ", "để hở")],
        "164.16": [("bùong trôi", "buông trôi"), ("xớ dính", "xơ dính")],
        "164.19": [("ở dùi", "ở đùi")],
        "164.21": [("mặt cá", "mắt cá")],
        "165.6": [("sọ dính", "sẹo dính")],
        "165.10": [("Bỏ bột", "Bó bột")],
        "165.14": [("bột cố", "bột có"), ("tỷ để", "tỳ để")],
        "165.20": [("lặp lại", "lập lại")],
        "166.4": [("động mạch chân", "động mạch chày")],
        "166.9": [("chân mác", "chày mác")],
        "166.14": [("gãy nát", "gãy vát")],
        "167.2": [("hông khớp", "hỏng khớp")],
        "167.4": [
            ("với chèo", "vỡ chéo"),
            ("với nhiều", "vỡ nhiều"),
            ("với xương", "vỡ xương"),
            ("ngực thấp", "ngực thắt"),
        ],
        "167.5": [("thủ nắn", "thử nắn")],
        "167.7": [("sẽ hông", "sẽ hỏng"), ("thì hông", "thì hỏng")],
        "167.8": [
            ("quần băng", "quấn băng"),
            ("chớ", "chờ"),
            ("hằn sưng", "hẳn sưng"),
            ("tại chỗ chân. Da cấu", "tại chỗ chân, da cấu"),
        ],
        "167.9": [("Mổ đồ đang", "Mổ dở dang")],
        "168.4": [("đầy toác", "đẩy toác")],
        "168.9": [("ĐI CHỨNG", "DI CHỨNG")],
        "168.14": [("Loạn đường", "Loạn dưỡng")],
        "168.15": [("Viêm hoại cục khớp", "Vôi hoá cạnh khớp")],
    }.items():
        patch(s, p, key, *pairs)
    s["nodes"] = {
        "N1": keep(ranges=[[163, 1, 17], [164, 0, 4]]),
        "N6": keep(ranges=[[163, 14, 17]]),
        "N7": keep(ranges=[[164, 18, 19], [165, 0, 7]]),
        "N12": keep(
            "Điểm đau chói trên dây chằng sên-mác trước hoặc gót-mác", [[163, 9, 11]]
        ),
        "N15": keep(ranges=[[164, 0, 4]]),
        "N21": keep(ranges=[[164, 4, 22], [165, 0, 7]]),
        "N22": keep(ranges=[[168, 0, 6]]),
        "N23": keep("Thử nắn bảo tồn gãy mắt cá trật xương sên", [[167, 5, 7]]),
        "N25": keep(ranges=[[165, 11, 21], [167, 11, 16]]),
        "N27": keep("Bắt vít cố định tam giác Volkmann", [[168, 0, 6]]),
        "N28": keep(ranges=[[167, 16, 19]]),
        "N29": keep(ranges=[[168, 6, 9]]),
        "N30": keep("Phẫu thuật gãy cổ chân mất vững và thời điểm mổ", [[167, 6, 10]]),
        "N31": merge(
            "N36",
            "Đề xuất nằm trong mục3.3 gãy mắt cá/trật chày-sên/toác gọng; dùng cùng thực thể N36 và giữ nguồn.",
        ),
        "N32": keep(ranges=[[167, 11, 16]]),
        "N34": keep("Gãy mắt cá thứ3 (tam giác Volkmann)", [[168, 0, 6]]),
        "N36": keep(
            "Gãy mắt cá trật xương sên",
            [[165, 21, 23], [166, 0, 15], [167, 0, 10], [168, 10, 20]],
        ),
        "N40": keep("Loạn dưỡng Sudeck sau gãy cổ chân", [[168, 14, 15]]),
        "N43": keep("Vôi hoá cạnh khớp và màng liên cốt", [[168, 15, 16]]),
    }
    s["edges"] = {
        "E19": keep(
            condition="Gãy cổ chân KHÔNG VỮNG ở người trẻ; thời điểm theo tình trạng sưng/phỏng",
            ranges=[[167, 6, 10]],
        ),
        "E25": keep(
            ranges=[[168, 17, 19]],
            condition="Người trẻ, mổ sớm cố định vững và tập sớm; số35ngày là kết quả được sách báo cáo",
        ),
        "E28": keep(
            condition="Nhóm bó bột không mổ được so sánh kết quả107ngày, không tự suy ra chỉ định từ con số"
        ),
    }
    s["held"]["H6"] = merge(
        "N25", "Cùng gãy mắt cá ngoài, tên OCR mất cá được sửa đúng ảnh."
    )
    for h, name, rg in [
        (5, "Trật khớp đơn thuần cổ chân", [[165, 8, 11]]),
        (7, "Mổ cấp cứu nắn và khâu dây chằng trật hở cổ chân", [[165, 8, 11]]),
        (8, "Mổ cố định xương mác khi gãy mắt cá ngoài lệch khớp", [[165, 16, 21]]),
        (
            9,
            "Viêm khớp thoái hoá sau chấn thương cổ chân",
            [[165, 8, 11], [165, 16, 21]],
        ),
        (20, "Chụp Xquang cổ chân xoay trong20độ", [[166, 4, 6]]),
        (21, "Gãy mắt cá ngoài thấp dưới chỗ nối chày-mác", [[167, 11, 15]]),
        (
            22,
            "Gãy cao ở1/3dưới xương mác trong gãy cổ chân",
            [[167, 11, 12], [167, 15, 16]],
        ),
        (23, "Gãy mắt cá trong", [[167, 16, 19]]),
    ]:
        s["held"][f"H{h}"] = recover(name, rg)
    for h, left, right, rel, rg in [
        (0, "N1", "N15", "MANAGED_BY", [[164, 0, 4]]),
        (1, "H5", "H7", "MANAGED_BY", [[165, 8, 11]]),
        (2, "H5", "H9", "MAY_CAUSE", [[165, 8, 11]]),
        (3, "N25", "H8", "MANAGED_BY", [[165, 16, 21]]),
        (4, "N25", "H9", "MAY_CAUSE", [[165, 16, 21]]),
        (13, "N36", "H20", "EVALUATED_BY", [[166, 4, 6]]),
        (14, "H21", "N25", "IS_A", [[167, 11, 15]]),
        (15, "H22", "N25", "IS_A", [[167, 11, 12], [167, 15, 16]]),
        (16, "H23", "N28", "MANAGED_BY", [[167, 16, 19]]),
        (17, "N34", "N22", "MANAGED_BY", [[168, 0, 6]]),
        (18, "N34", "N27", "MANAGED_BY", [[168, 0, 6]]),
    ]:
        s["held"][f"H{h}"] = edge(left, right, rel, rg)
    for h, c in {
        0: "Một trong2cách cho bong gân nặng; nghiên cứu sách báo nhóm mổ kém hơn",
        1: "Trật khớp hở có vết thương",
        3: "Gãy cao/ngang khe khớp, còn lệch sên hoặc khe khớp rộng; cần lập lại giải phẫu100%",
        4: "Sên còn lệch ra ngoài1mm theo nghiên cứu được sách nêu",
        17: "Mảnh>1/4–1/3diện khớp HOẶC khấp khểnh>2mm",
        18: "Có chỉ định mổ theo kích thước/khấp khểnh; hai hướng vít là lựa chọn khác nhau",
    }.items():
        s["held"][f"H{h}"]["condition"] = c
    s["missing"] = [
        {
            "pdf_pages": [166, 167],
            "kind": "missing_classification_parent",
            "reason": "Ba cơ chế vẹo ngoài/vẹo trong/nén trục chưa có Classification được LLM đề xuất; giữ category ngoài quan hệ HAS_CATEGORY từ Condition, không phát minh cha.",
        },
        {
            "pdf_pages": [163, 164, 165, 167, 168],
            "kind": "printed_claims_preserved",
            "reason": "Denta,8dâychằng,ruỗi bàn chân,42%/80%,35/107ngày giữ theo bản2006; chưa cập nhật sang hướng dẫn hiện hành hoặc suy ra tiên lượng cá nhân.",
        },
    ]
    return s


REVIEWED = {
    3: lesson3,
    4: lesson4,
    5: lesson5,
    6: lesson6,
    7: lesson7,
    8: lesson8,
    9: lesson9,
    10: lesson10,
    11: lesson11,
    12: lesson12,
    13: lesson13,
    14: lesson14,
    16: lesson16,
    17: lesson17,
    18: lesson18,
    19: lesson19,
    20: lesson20,
    21: lesson21,
    22: lesson22,
    23: lesson23,
    24: lesson24,
    25: lesson25,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lessons", type=int, nargs="+")
    args = parser.parse_args()
    for number in args.lessons:
        if number not in REVIEWED:
            raise ValueError("chapter_not_yet_manually_reviewed")
        write_json(WORK / f"bai-{number:02d}/decisions-input.json", REVIEWED[number]())


if __name__ == "__main__":
    main()
