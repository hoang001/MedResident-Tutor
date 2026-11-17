"""PMC ESearch/ESummary + the official 2026 cloud distribution, not HTML crawling."""
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlencode, urlsplit

from .io import DATA, read, sha, write

S3 = "https://pmc-oa-opendata.s3.amazonaws.com/"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
XLINK = "{http://www.w3.org/1999/xlink}href"


def cloud_url(url):
    if url.startswith("s3://pmc-oa-opendata/"):
        return S3 + url.removeprefix("s3://pmc-oa-opendata/")
    if not url.startswith(S3):
        raise ValueError("non_official_cloud_asset")
    return url


def text(element):
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def query_url(command, **params):
    return EUTILS + command + ".fcgi?" + urlencode(params)


def discover(fetcher, per_group=15):
    if not 1 <= per_group <= 250:
        raise ValueError("candidate_limit_1_to_250_per_group")
    queries = {
        "orthopedics": [
            '(fracture[Title] AND (radius[Title] OR femur[Title] OR humerus[Title]))',
            '(dislocation[Title] AND (shoulder[Title] OR elbow[Title] OR hip[Title]))',
            '("compartment syndrome"[Title] NOT abdominal[Title] NOT "case series"[Title])',
            '((axillary[Title] OR popliteal[Title]) AND artery[Title])',
            '(atlantoaxial[Title] AND (trauma[Title] OR traumatic[Title]))',
        ],
        "surgical_emergency": [
            'appendicitis[Title]', '"bowel obstruction"[Title]',
            '(perforation[Title] AND (intestinal[Title] OR duodenal[Title]))',
            '(trauma[Title] AND (abdominal[Title] OR splenic[Title]))', '"acute abdomen"[Title]',
        ],
    }
    candidates = []
    for specialty, terms in queries.items():
        chosen, queries_by_id = [], {}
        for i, term in enumerate(terms):
            count = per_group // len(terms) + (i < per_group % len(terms))
            if not count:
                continue
            query = '"J Surg Case Rep"[journal] AND cc by license[filter] AND ' + term
            ids, _ = fetcher.json(query_url("esearch", db="pmc", term=query, retmode="json", retmax=count, sort="relevance"))
            for uid in ids["esearchresult"]["idlist"]:
                if uid not in queries_by_id:
                    chosen.append(uid)
                    queries_by_id[uid] = query
        records, _ = fetcher.json(query_url("esummary", db="pmc", id=",".join(chosen), retmode="json"))
        for uid in chosen:
            record = records["result"][uid]
            doi = next((a["value"] for a in record.get("articleids", []) if a.get("idtype") == "doi"), None)
            candidates.append({"source_id": "SRC_CASE_PMC" + uid, "pmcid": "PMC" + uid,
                               "doi": doi, "title": record["title"], "authors": record.get("authors", []),
                               "publication_date": record.get("pubdate"), "specialty": specialty,
                               "original_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC" + uid + "/",
                               "query": queries_by_id[uid], "status": "metadata_candidate_needs_case_and_license_review",
                               "rare_or_variant_title_flag": bool(re.search(r"rare|unusual|uncommon|atypical|unique", record["title"], re.I)),
                               "diagnosis_is_not_general_answer_key": True})
    unique = {}
    for candidate in candidates:
        unique.setdefault(candidate["doi"] or candidate["pmcid"], candidate)
    # Preserve previously reviewed metadata candidates rather than silently replacing them.
    path = DATA / "catalog/candidates.json"
    if path.exists():
        for candidate in read(path):
            unique.setdefault(candidate["doi"] or candidate["pmcid"], candidate)
    excluded_path = DATA / "catalog/excluded-candidates.json"
    if excluded_path.exists():
        excluded = {c["pmcid"] for c in read(excluded_path)["candidates"]}
        unique = {key: candidate for key, candidate in unique.items() if candidate["pmcid"] not in excluded}
    write(DATA / "catalog/candidates.json", list(unique.values()))
    return list(unique.values())


def metadata(fetcher, pmcid):
    if not re.fullmatch(r"PMC\d+", pmcid):
        raise ValueError("invalid_pmcid")
    body, _ = fetcher.get(S3 + "?" + urlencode({"list-type": 2, "prefix": pmcid + ".", "delimiter": "/"}))
    root = ET.fromstring(body)
    ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    versions = [e.text.rstrip("/") for e in root.findall("s:CommonPrefixes/s:Prefix", ns)]
    for version in sorted(versions):
        record, audit = fetcher.json(S3 + version + "/" + version + ".json")
        write(DATA / "raw/pmc" / (version + ".json"), record)
        if (str(record.get("license_code", "")).lower().replace(" ", "-") == "cc-by"
                and record.get("is_manuscript") in (False, "no", None)
                and record.get("is_retracted") in (False, "no", None)):
            return record, audit
    raise ValueError("no_nonretracted_published_CC_BY_version")


def blocks_and_figures(xml):
    root = ET.fromstring(xml)
    article = root if root.tag == "article" else root.find(".//article")
    if article is None:
        raise ValueError("jats_article_missing")
    blocks, figures = [], []

    def visit(element, path, section=""):
        if element.tag == "sec":
            section = text(element.find("title")) or section
        if element.tag == "p" and "/body/" in path and "/fig[" not in path and "/table-wrap[" not in path:
            blocks.append({"block_id": f"p{len(blocks)+1:03d}", "locator": path, "section": section, "text": text(element)})
        counts = {}
        for child in element:
            counts[child.tag] = counts.get(child.tag, 0) + 1
            suffix = f"[{counts[child.tag]}]" if child.tag not in ("body", "front", "back") else ""
            visit(child, path + "/" + child.tag + suffix, section)
    visit(article, "/article")
    for figure in article.findall(".//fig"):
        graphics = figure.findall(".//graphic")
        figures.append({"figure_id": figure.get("id"), "label": text(figure.find("label")),
                        "caption": text(figure.find("caption")), "credit": text(figure.find("permissions")),
                        "graphics": [g.get(XLINK) for g in graphics],
                        "locator": "/article//fig[@id='" + str(figure.get("id")) + "']"})
    licenses = article.findall(".//article-meta/permissions/license")
    license_urls = sorted({url for lic in licenses for node in lic.iter()
                           for url in [node.get(XLINK), node.text if node.tag.endswith("license_ref") else None]
                           if url and "creativecommons.org/licenses/" in url})
    authors = [text(n.find("given-names")) + " " + text(n.find("surname"))
               for n in article.findall("./front/article-meta/contrib-group/contrib/name")]
    return {"blocks": blocks, "figures": figures, "license_urls": license_urls,
            "license_text": " ".join(text(lic) for lic in licenses), "authors": authors,
            "title": text(article.find("./front/article-meta/title-group/article-title")),
            "publication_year": article.findtext("./front/article-meta/pub-date/year"),
            "article_type": article.get("article-type"), "xml_sha256": sha(xml)}


def prepare(fetcher, pmcid):
    record, audit = metadata(fetcher, pmcid)
    url = cloud_url(record["xml_url"])
    xml, _ = fetcher.get(url, expected_md5=parse_qs(urlsplit(url).query).get("md5", [None])[0])
    parsed = blocks_and_figures(xml)
    if not any(u and re.search(r"creativecommons.org/licenses/by/\d", u) for u in parsed["license_urls"]):
        raise ValueError("explicit_article_CC_BY_license_required")
    write(DATA / "raw/pmc" / (pmcid + "-parsed.json"), parsed)
    (DATA / "raw/pmc" / (pmcid + ".xml")).write_bytes(xml)
    write(DATA / "raw/pmc" / (pmcid + "-record.json"), {"metadata": record, "retrieval": audit})
    return parsed


def media_url(record, graphic):
    # Match the actual graphic asset, never choose an arbitrary first image/thumbnail.
    matches = []
    for url in record.get("media_urls", []):
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        if name == graphic or stem == graphic:
            matches.append(url)
    if len(matches) != 1:
        raise ValueError("figure_asset_not_unique:" + str(graphic))
    return cloud_url(matches[0])
