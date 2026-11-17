import asyncio
import json
import subprocess
import sys
from pathlib import Path

from .common import ROOT, RUN, DOCKER, digest, inside, sha, write


async def inventory():
    import app.models  # noqa: F401
    from sqlalchemy import text
    from app.core.database import engine
    from app.modules.knowledge.service import get_graph_store
    inventory = {}
    async with engine.connect() as c:
        await c.execute(text("SET TRANSACTION READ ONLY"))
        for name in ("users", "questions", "rubrics", "rubric_criteria", "rubric_criterion_source_units", "documents", "source_units", "practice_attempts", "study_records", "study_sessions", "knowledge_reviews", "topics", "specialties"):
            rows = (await c.execute(text('SELECT row_to_json(t)::text FROM "' + name + '" t'))).scalars().all()
            inventory[name] = [json.loads(row) for row in rows]
    write("backup/rows-before.private.json", inventory)
    write("inventory-before.json", {"counts":{k:len(v) for k,v in inventory.items()},
        "available":sum(q["is_available"] for q in inventory["questions"]),
        "protected_rows":{k:digest(v) for k,v in inventory.items() if k in ("users", "practice_attempts", "study_records", "study_sessions", "knowledge_reviews")}})
    graph = get_graph_store()
    try:
        snapshot = await graph.snapshot()
        rows = [n for n in snapshot.nodes.values() if n["type"] == "SampleQuestion"]
        write("book-question-candidates.json", rows)
        write("graph-counts-before.json", {"nodes":len(snapshot.nodes), "edges":len(snapshot.edges), "book_questions":len(rows)})
    finally:
        await graph.close()
    print(json.dumps({"questions":len(inventory["questions"]),"published":sum(q["is_available"] for q in inventory["questions"]),"book_question_candidates":len(rows)}))


def sources():
    sys.path.insert(0, str(RUN / "deps"))
    from pypdf import PdfReader
    catalog = json.loads((ROOT / "data/library/catalog.json").read_text(encoding="utf-8"))
    windows = [json.loads(l) for l in (ROOT / "data/retrieval/book-corpus-v1/corpus.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    source_pages, source_catalog = {}, {}
    for book, filename in zip(catalog["books"], ("Cap-cuu-Ngoai-khoa-Chan-thuong-DH-Y-Ha-Noi", "DVC.005844"), strict=True):
        ocr_path = ROOT / "data/graduate" / (filename + ".json")
        ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
        pdf = ROOT / "data/raw-source" / book["filename"]
        if not pdf.is_file(): pdf = ROOT / "data/raw-source" / (filename + ".pdf")
        assert pdf.is_file() and sha(pdf) == book["sha256"]
        pdf_pages = len(PdfReader(pdf).pages)
        assert pdf_pages == book["pages"] == ocr["page_count"]
        source_catalog[book["id"]] = {**book, "pdf_path":pdf.relative_to(ROOT).as_posix(), "ocr_path":ocr_path.relative_to(ROOT).as_posix(), "ocr_sha256":sha(ocr_path), "source_type":"textbook"}
        for section in ocr["sections"]:
            page = section["page_start"]
            chunks = sorted([w for w in windows if w["source_id"] == book["id"] and w["page"] == page], key=lambda w:w.get("start",0))
            full = ""
            for w in chunks:
                start = w.get("start",0)
                if start <= len(full): full += w["content"][max(0,len(full)-start):]
            content = full if full else section["text"]
            source_pages[book["id"]+":"+str(page)] = {"source_id":book["id"],"page":page,"content":content,
                "text_version_sha256":digest(content),"origin":"reviewed_source_corpus" if full else "existing_book_ocr"}
    for filename, sid in (("Quy-trình-PT-Chấn-thương.pdf","SRC_ORTHO_PROCEDURES_MOH_2017_001"), ("HuongdanquytrinhkythuatNgoaikhoa- Chanthuongchinhhinh.pdf","SRC_ORTHO_PROCEDURES_MOH_2014_001")):
        pdf = next((ROOT/"data/raw-source").rglob(filename))
        reader = PdfReader(pdf)
        source_catalog[sid] = {"id":sid,"title":filename[:-4],"year":None,"pages":len(reader.pages),"pdf_path":pdf.relative_to(ROOT).as_posix(),"sha256":sha(pdf),"source_type":"procedure","metadata_status":"decision_and_scope_to_verify"}
        for i,page in enumerate(reader.pages,1):
            content = page.extract_text() or ""
            source_pages[sid+":"+str(i)] = {"source_id":sid,"page":i,"content":content,"text_version_sha256":digest(content),"origin":"original_pdf_text_extraction_no_ocr"}
    write("source-pages.json", source_pages)
    write("source-catalog.json", source_catalog)
    write("protected-files.json", {p.relative_to(ROOT).as_posix():sha(p) for base in (ROOT/"data/processed",ROOT/"data/integration",ROOT/"data/graduate",ROOT/"model-training/src",ROOT/"adapter") for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts})
    print(json.dumps({"sources":len(source_catalog),"pages":len(source_pages)}))


def main():
    if "--inside" in sys.argv: return asyncio.run(inventory())
    backup = RUN / "backup/postgres.dump"
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        with backup.open("wb") as f:
            subprocess.run([DOCKER,"exec","medresident-tutor-db-1","sh","-c",'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],stdout=f,check=True)
        assert backup.stat().st_size > 1000
        write("backup/manifest.json", {"format":"pg_dump_custom","file":"postgres.dump","sha256":sha(backup)})
        inside("prepare")
    sources()


if __name__ == "__main__": main()
