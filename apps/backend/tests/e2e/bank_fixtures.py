"""Synthetic, nonclinical PDF and SourceUnits for isolated tests only."""

import hashlib

from sqlalchemy import select

from app.modules.documents.models import Document
from app.modules.documents.source_units import SourceUnit


def synthetic_pdf():
    stream = b"BT /F1 12 Tf 30 70 Td (Synthetic nonclinical test evidence A and B) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 100] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for n, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += str(n).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        data += f"{offset:010d} 00000 n \n".encode()
    return (
        data
        + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref).encode()
        + b"\n%%EOF\n"
    )


async def seed_sources(session, admin_id, storage_root):
    doc = await session.scalar(
        select(Document).where(Document.external_id == "FIXTURE_SOURCE_BANK")
    )
    if doc is None:
        content = synthetic_pdf()
        storage_root.mkdir(parents=True, exist_ok=True)
        (storage_root / "bank-fixture.pdf").write_bytes(content)
        doc = Document(
            external_id="FIXTURE_SOURCE_BANK",
            name="Synthetic source for question-bank tests",
            original_filename="bank-fixture.pdf",
            storage_path="bank-fixture.pdf",
            mime_type="application/pdf",
            file_size=len(content),
            created_by=admin_id,
            source_sha256=hashlib.sha256(content).hexdigest(),
            import_metadata={"catalog": {"title": "Synthetic source for question-bank tests"}},
        )
        session.add(doc)
        await session.flush()
        for letter in ("A", "B"):
            session.add(
                SourceUnit(
                    external_id="FIXTURE_SU_" + letter,
                    document_id=doc.id,
                    title="Synthetic evidence " + letter,
                    content="Synthetic nonclinical evidence "
                    + letter
                    + " for testing question criteria and mappings only.",
                    pdf_page_start=1,
                    pdf_page_end=1,
                    printed_page_start=10,
                    printed_page_end=10,
                    import_metadata={
                        "expert_review": {"status": "unverified"},
                        "dataset_fields": {"validation_status": "synthetic_fixture"},
                    },
                )
            )
    await session.flush()
