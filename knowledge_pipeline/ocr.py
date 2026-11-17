"""Optional local OCR callback. No cloud service or weights download."""

import hashlib
import json
from pathlib import Path
import subprocess


def provided_ocr_json(root, books, folder):
    """Read supplied page OCR verbatim; never invoke an OCR engine or a model."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if not folder.is_relative_to(root) or not folder.is_dir():
        raise ValueError("OCR JSON folder must exist inside repository")
    pages_by_pdf, artifacts = {}, []
    for book in books:
        pdf = (root / book["repo_relative_path"]).resolve()
        if not pdf.is_relative_to(root) or not pdf.is_file():
            raise ValueError("Original PDF must exist inside repository")
        artifact = folder / (pdf.stem + ".json")
        data = json.loads(artifact.read_text(encoding="utf-8-sig"))
        pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if data.get("source_sha256") != pdf_hash:
            raise ValueError("Provided OCR does not match original PDF SHA-256")
        from pypdf import PdfReader

        count = len(PdfReader(pdf).pages)
        if data.get("page_count") != count:
            raise ValueError("OCR page count does not match PDF")
        pages = {}
        for row in data.get("sections", []):
            number = row.get("page_start")
            if (type(number) is not int or not 1 <= number <= count
                    or row.get("page_end") != number or number in pages
                    or not isinstance(row.get("text"), str)):
                raise ValueError("OCR sections need unique 1-based individual PDF pages")
            pages[number] = row["text"]
        pages_by_pdf[pdf] = pages
        artifacts.append({
            "document_edition_id": book["document_edition_id"],
            "path": artifact.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "source_pdf_sha256": pdf_hash,
            "model": data.get("model"),
            "reported_status": data.get("status"),
            "reported_unreadable_pages": data.get("unreadable_pages", []),
            "reported_failures": data.get("failures", []),
            "page_count": count,
            "provided_pages": sorted(pages),
            "expert_review": "unverified",
        })

    def callback(pdf_path, page_number):
        pages = pages_by_pdf[Path(pdf_path).resolve()]
        if page_number not in pages:
            raise ValueError("Requested page is absent from supplied OCR")
        return pages[page_number]

    return callback, {"engine": "provided-ocr-json", "artifacts": artifacts,
                      "page_numbering": "pdf-1-based", "new_ocr_calls": 0}


def local_ocr(tessdata, *, language="vie+eng", dpi=200):
    import pymupdf

    folder = Path(tessdata).resolve()
    hashes = {}
    for lang in language.split("+"):
        file = folder / f"{lang}.traineddata"
        if not file.is_file():
            raise ValueError(f"Missing OCR language data: {lang}.traineddata")
        hashes[lang] = hashlib.sha256(file.read_bytes()).hexdigest()

    def callback(pdf_path, page_number):
        with pymupdf.open(pdf_path) as doc:
            page = doc[page_number - 1]
            tp = page.get_textpage_ocr(
                language=language, dpi=dpi, full=True, tessdata=str(folder)
            )
            return page.get_text("text", textpage=tp)

    return callback, {
        "engine": "pymupdf-tesseract",
        "version": pymupdf.VersionBind,
        "language": language,
        "dpi": dpi,
        "traineddata_sha256": hashes,
    }


def subprocess_ocr(python, tessdata):
    """Use an already installed local OCR runtime without changing its environment."""
    python, tessdata = Path(python).resolve(), Path(tessdata).resolve()
    if not python.is_file():
        raise ValueError("OCR Python not found")
    probe = subprocess.run(
        [str(python), "-c", "import pymupdf;print(pymupdf.VersionBind)"],
        capture_output=True,
        text=True,
        check=True,
    )
    hashes = {
        lang: hashlib.sha256(
            (tessdata / f"{lang}.traineddata").read_bytes()
        ).hexdigest()
        for lang in ("vie", "eng")
    }
    script = """import pymupdf,sys,json
with pymupdf.open(sys.argv[1]) as d:
 p=d[int(sys.argv[2])-1]
 t=p.get_textpage_ocr(language='vie+eng',dpi=200,full=True,tessdata=sys.argv[3])
 print(json.dumps(p.get_text('text',textpage=t),ensure_ascii=True))
"""

    def callback(pdf_path, page_number):
        result = subprocess.run(
            [str(python), "-c", script, str(pdf_path), str(page_number), str(tessdata)],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return json.loads(result.stdout)

    return callback, {
        "engine": "pymupdf-tesseract",
        "version": probe.stdout.strip(),
        "language": "vie+eng",
        "dpi": 200,
        "traineddata_sha256": hashes,
    }
