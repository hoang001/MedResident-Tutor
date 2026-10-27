"""Optional local OCR callback. No cloud service or weights download."""

import hashlib
import json
from pathlib import Path
import subprocess


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
