import hashlib

import pytest

from document_toolkit.common import write_json
from knowledge_pipeline.hmu_public import (
    course_listings,
    extract_plos,
    parse_html,
    validate_hmu_url,
)
from scripts import supplement_hmu_curriculum as supplement

HTML = '<div class="coursebox" data-courseid="27"><h3 class="coursename">CS034. Kỹ năng lâm sàng Ngoại khoa cơ bản</h3><div class="summary">Kỹ năng lâm sàng Ngoại khoa cơ bản</div></div>'


def test_hmu_allowlist_refuses_external_or_lookalike_publishers():
    validate_hmu_url("https://lms.hmu.edu.vn/course/info.php?id=27")
    for url in [
        "https://hmu.edu.vn.example.com/page",
        "https://example.com/hmu.edu.vn",
        "https://user:password@lms.hmu.edu.vn/page",
        "http://lms.hmu.edu.vn/page",
    ]:
        with pytest.raises(ValueError, match="source_is_not_hmu_https"):
            validate_hmu_url(url)


def test_listing_is_metadata_and_does_not_collect_login_or_script_content():
    data = "<script>Fake course and secret code</script><nav>Đăng nhập</nav>" + HTML
    rows = course_listings(data)
    assert len(rows) == 1
    assert rows[0]["course_code"] == "CS034"
    assert rows[0]["summary"] == rows[0]["course_name"]
    assert "Fake course" not in parse_html(data).text()


def test_plo_offsets_keep_negation_conditions_and_domain_across_pages():
    pages = [
        "2.4. Hệ thống\nPLO9: Không bỏ điều kiện khi đánh giá.\n",
        "PLO10: Đánh giá trên cơ sở toàn diện.\n2.5. Phát triển bản thân\nPLO 11. Tự học theo nguồn.\n",
    ]
    rows = extract_plos(pages)
    assert [r["code"] for r in rows] == ["PLO9", "PLO10", "PLO11"]
    assert rows[1]["domain"] == rows[0]["domain"] == "2.4. Hệ thống"
    assert rows[2]["domain"] == "2.5. Phát triển bản thân"
    assert "Không bỏ điều kiện" in rows[0]["quote"]
    assert "2.5." not in rows[1]["quote"]
    assert all(pages[r["page"] - 1][r["start"] : r["end"]] == r["quote"] for r in rows)


def test_duplicate_plo_numbers_cannot_silently_overwrite():
    with pytest.raises(ValueError, match="duplicate_hmu_plo_code"):
        extract_plos(["PLO1: One.\nPLO1: Different.\n"])


def test_evidence_requires_exact_quote_and_the_original_source_url(
    tmp_path, monkeypatch
):
    folder = tmp_path / "discovery"
    folder.mkdir()
    path = folder / "course.html"
    path.write_text(HTML, encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    url = "https://lms.hmu.edu.vn/course/index.php?categoryid=2419"
    write_json(path.with_suffix(".json"), {"url": url, "sha256": sha})
    monkeypatch.setattr(supplement, "ROOT", tmp_path)
    monkeypatch.setattr(supplement, "CACHE", folder)
    ev = {
        "snapshot_path": "discovery/course.html",
        "source_url": url,
        "source_sha256": sha,
        "locator": {"kind": "course_title", "lms_course_id": "27"},
        "quote": course_listings(HTML)[0]["title"],
    }
    supplement.validate_evidence(ev)
    with pytest.raises(ValueError, match="hmu_quote_does_not_match_locator"):
        supplement.validate_evidence({**ev, "quote": "Unsupported learning outcome"})
    with pytest.raises(ValueError, match="hmu_source_url_mismatch"):
        supplement.validate_evidence(
            {
                **ev,
                "source_url": "https://lms.hmu.edu.vn/course/index.php?categoryid=2421",
            }
        )
