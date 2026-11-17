"""Offline parser, identity, source, ZIP and checkpoint tests. No models or DB."""
import hashlib
import io
import json
import zipfile

import httpx
import pytest

from .build import excerpt, validate
from .contracts import validate_records
from .graz import RemoteZip
from .io import DATA, Fetcher, safe_url, sha
from .pmc import blocks_and_figures, cloud_url, media_url

JATS = b'''<article article-type="case-report"><front><article-meta><title-group><article-title>Test case</article-title></title-group><permissions><license><license-p>CC BY <ext-link xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="https://creativecommons.org/licenses/by/4.0/">4.0</ext-link></license-p></license></permissions></article-meta></front><body><sec><title>Case 1</title><p>Patient has <italic>pain</italic>. CT confirmed X. Treated Y.</p><fig id="f1"><label>Figure 1</label><caption><p>CT from Case 1.</p></caption><graphic xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="image1"/></fig></sec><sec><title>Case 2</title><p>Other patient.</p></sec></body></article>'''


def test_jats_keeps_case_grouping_and_excludes_caption_from_case_paragraphs():
    parsed = blocks_and_figures(JATS)
    assert len(parsed["blocks"]) == 2
    assert parsed["blocks"][0]["section"] == "Case 1"
    assert parsed["blocks"][1]["section"] == "Case 2"
    assert parsed["blocks"][0]["locator"] == "/article/body/sec[1]/p[1]"
    assert parsed["figures"][0]["caption"] == "CT from Case 1."
    assert parsed["license_urls"] == ["https://creativecommons.org/licenses/by/4.0/"]


def test_manual_excerpt_offsets_are_exact_and_do_not_add_knowledge():
    blocks = {b["block_id"]: b for b in blocks_and_figures(JATS)["blocks"]}
    selected, ref = excerpt({"block": "p001", "start": "CT confirmed", "end_before": "Treated"}, blocks)
    assert selected == "CT confirmed X. "
    assert blocks["p001"]["text"][ref["normalized_char_start"]:ref["normalized_char_end"]] == selected
    with pytest.raises(ValueError, match="start_marker_not_unique"):
        excerpt({"block": "p001", "start": "Not present"}, blocks)


def test_figure_asset_mapping_never_guesses_thumbnail_or_neighbor():
    record = {"media_urls": ["s3://pmc-oa-opendata/PMC1.1/image1.jpg?md5=abc", "s3://pmc-oa-opendata/PMC1.1/image2.jpg"]}
    assert media_url(record, "image1").endswith("image1.jpg?md5=abc")
    with pytest.raises(ValueError, match="figure_asset_not_unique"):
        media_url(record, "missing")
    record["media_urls"].append("s3://pmc-oa-opendata/PMC1.1/image1.png")
    with pytest.raises(ValueError, match="figure_asset_not_unique"):
        media_url(record, "image1")


@pytest.mark.parametrize("url", ["http://10.8.0.1:4000/v1/chat/completions", "https://localhost/a", "https://example.com/image", "file:///secret", "https://user:pass@api.figshare.com/a"])
def test_collector_refuses_model_local_and_unapproved_urls(url):
    with pytest.raises(ValueError):
        safe_url(url)


def test_only_the_official_pmc_bucket_is_accepted():
    assert cloud_url("s3://pmc-oa-opendata/PMC1.1/a.xml").startswith("https://pmc-oa-opendata.s3.amazonaws.com/")
    with pytest.raises(ValueError):
        cloud_url("s3://other-bucket/a.xml")


def fake_fetcher(tmp_path, handler):
    fetcher = Fetcher(tmp_path)
    fetcher.client.close()
    fetcher.client = httpx.Client(transport=httpx.MockTransport(handler))
    return fetcher


def test_successful_download_is_cached_and_resume_uses_zero_requests(tmp_path):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"original", headers={"content-type": "image/png"})
    f = fake_fetcher(tmp_path, handler)
    body, meta = f.get("https://api.figshare.com/test", expected_md5=hashlib.md5(b"original").hexdigest())
    assert meta["sha256"] == sha(body)
    assert f.get("https://api.figshare.com/test")[0] == body
    assert len(seen) == 1 and f.cache_hits == 1
    body_path = tmp_path / meta["cache_path"]
    body_path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checkpoint_hash_mismatch"):
        f.get("https://api.figshare.com/test")


def test_incorrect_md5_never_creates_success_checkpoint(tmp_path):
    f = fake_fetcher(tmp_path, lambda request: httpx.Response(200, content=b"wrong"))
    with pytest.raises(ValueError, match="publisher_md5_mismatch"):
        f.get("https://api.figshare.com/test", expected_md5="0" * 32)
    assert not list(tmp_path.glob("raw/http/*.json"))


def test_range_ignored_by_server_never_downloads_full_archive(tmp_path):
    f = fake_fetcher(tmp_path, lambda request: httpx.Response(200, content=b"full archive"))
    with pytest.raises(ValueError, match="range_not_supported"):
        f.get("https://api.figshare.com/test", headers={"Range": "bytes=0-10"})


def test_remote_zip_reads_correct_member_and_checks_crc():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("images/a.png", b"first exact bytes")
        z.writestr("images/b.png", b"second exact bytes")
    archive = b.getvalue()
    class Fake:
        def get(self, url, headers, maximum):
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
            return archive[start:end+1], {"content_range": f"bytes {start}-{end}/{len(archive)}"}
    r = RemoteZip(Fake(), {"size": len(archive), "download_url": "https://api.figshare.com/test", "id": 1})
    body, proof = r.member("images/b.png")
    assert body == b"second exact bytes"
    assert proof["sha256"] == sha(body)
    assert proof["archive_md5_not_verified_partial_download"] is True
    r.members["images/b.png"].CRC ^= 1
    with pytest.raises(ValueError, match="crc_or_size"):
        r.member("images/b.png")


def test_real_local_collection_all_source_links_hashes_and_study_groups():
    report = validate()
    assert report["clinical_cases"] == 10
    assert report["case_specialties"] == {"orthopedics": 6, "surgical_emergency": 4}
    assert report["imaging_studies"] == 20 and report["dataset_images"] == 39
    assert report["VOC_YOLO_object_geometry_checks"] == 70
    assert report["expert_verified"] is False and report["authored_exercises"] == 0
    studies = json.loads((DATA / "processed/imaging-studies.json").read_text())
    assert len({s["patient_group_id"] for s in studies}) == 20
    cases = json.loads((DATA / "processed/clinical-cases.json").read_text(encoding="utf-8"))
    case = next(c for c in cases if c["article_group_id"] == "PMC8130875")
    assert case["patient_in_article"] == "case_1_of_2"
    assert not any(i.endswith("f4") for i in case["image_ids"])


def test_schema_does_not_accept_expert_verified_or_authored_case_confusion():
    cases = json.loads((DATA / "processed/clinical-cases.json").read_text(encoding="utf-8"))
    c = dict(cases[0], expert_verified=True)
    with pytest.raises(Exception):
        validate_records("ClinicalCase", [c])
    c = dict(cases[0], data_kind="authored_exercise")
    with pytest.raises(Exception):
        validate_records("ClinicalCase", [c])


def test_image_belongs_to_exactly_one_case_or_study():
    images = json.loads((DATA / "processed/case-images.json").read_text(encoding="utf-8"))
    for fields in ({"case_id": None, "study_id": None}, {"case_id": "CASE_1", "study_id": "STUDY_1"}):
        with pytest.raises(Exception):
            validate_records("MedicalImage", [{**images[0], **fields}])
