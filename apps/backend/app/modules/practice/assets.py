"""Whitelist learner projections and authenticated file delivery for authored exercises."""

import asyncio
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.integration.inputs import digest
from app.storage.local import LocalFileStorage


def authored_metadata(metadata):
    return (metadata or {}).get("dataset_fields", {}).get("clinical_exercise")


def learner_view(authored, prefix, *, structured=False):
    if not authored:
        return None
    learner = authored["learner"]
    return {
        "title": learner["title"],
        "presentation": learner["presentation"],
        "question": (
            "Trả lời bằng các lựa chọn ở từng phần bên dưới. Có thể thêm giải thích ngắn, "
            "chưa tính điểm."
            if structured
            else learner["question"]
        ),
        "notice": learner["notice"],
        "show_grid": bool(authored.get("show_grid")),
        "images": [
            {
                "asset_id": image["asset_id"],
                "alt": f"Ảnh {i} của bài tập",
                "width": image["width"],
                "height": image["height"],
                "url": prefix + "/assets/" + image["asset_id"],
            }
            for i, image in enumerate(learner["images"], 1)
        ],
    }


def solution_view(authored):
    return {
        "notice": "Đáp án do dự án biên soạn từ nguồn, chưa được chuyên gia duyệt.",
        "criteria": [
            {
                k: c[k]
                for k in (
                    "criterion_id",
                    "description",
                    "max_score",
                    "reference_answer_vi",
                    "acceptable_variants",
                )
            }
            for c in authored["criteria"]
        ],
        "annotations": authored["answer_annotations"],
        "source": {
            k: authored["source"][k]
            for k in ("title", "original_url", "license", "license_url", "attribution_text")
        },
        "page_basis": "compiled_packet_not_original_article",
    }


async def image_response(authored, asset_id, storage_root):
    if not authored or not re.fullmatch(r"[a-f0-9]{24}", asset_id):
        raise HTTPException(404, "Image not found")
    asset = next((a for a in authored["assets"] if a["asset_id"] == asset_id), None)
    if not asset or not re.fullmatch(
        r"clinical-exercises/[a-f0-9]{24}\.(png|jpg)", asset["storage_key"]
    ):
        raise HTTPException(404, "Image not found")
    path = LocalFileStorage(storage_root)._resolve(asset["storage_key"])
    if not path.is_file() or await asyncio.to_thread(digest, path) != asset["sha256"]:
        raise HTTPException(404, "Image unavailable or changed")
    return FileResponse(
        path,
        media_type=asset["mime_type"],
        filename="image-" + asset_id + path.suffix,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
