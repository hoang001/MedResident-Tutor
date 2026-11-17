"""Selective ZIP member retrieval from the publisher's Figshare image archives."""
import csv
import io
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import defaultdict

from PIL import Image

from .io import DATA, sha, write


class RemoteZip:
    def __init__(self, fetcher, file):
        self.fetcher, self.file = fetcher, file
        size = file["size"]
        tail = self.range(size - min(size, 65557), size - 1)
        position = tail.rfind(b"PK\x05\x06")
        if position < 0:
            raise ValueError("zip_eocd_missing")
        eocd = struct.unpack_from("<4s4H2LH", tail, position)
        _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = eocd
        if disk or cd_disk or disk_count != count or count == 65535 or cd_offset == 0xFFFFFFFF:
            raise ValueError("multidisk_or_zip64_not_supported")
        if cd_size > 4_000_000:
            raise ValueError("central_directory_exceeds_budget")
        central = self.range(cd_offset, cd_offset + cd_size - 1)
        fake_eocd = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, count, count, cd_size, 0, 0)
        # Only parse the central directory; never extract from this synthetic ZIP.
        self.members = {i.filename: i for i in zipfile.ZipFile(io.BytesIO(central + fake_eocd)).infolist()}

    def range(self, start, end):
        body, meta = self.fetcher.get(self.file["download_url"], headers={"Range": f"bytes={start}-{end}"}, maximum=end-start+1)
        if meta["content_range"] != f"bytes {start}-{end}/{self.file['size']}" or len(body) != end-start+1:
            raise ValueError("range_response_mismatch")
        return body

    def member(self, name):
        item = self.members[name]
        if item.file_size > 15_000_000 or item.compress_size > 15_000_000:
            raise ValueError("zip_member_exceeds_budget")
        head = self.range(item.header_offset, item.header_offset + 29)
        fields = struct.unpack("<4s5H3L2H", head)
        if fields[0] != b"PK\x03\x04" or fields[2] & 1:
            raise ValueError("invalid_or_encrypted_local_header")
        name_length, extra_length = fields[-2:]
        start = item.header_offset + 30
        payload = self.range(start, start + name_length + extra_length + item.compress_size - 1)
        if payload[:name_length].decode("utf-8") != name:
            raise ValueError("zip_member_filename_mismatch")
        compressed = payload[name_length + extra_length:]
        if item.compress_type == zipfile.ZIP_DEFLATED:
            inflater = zlib.decompressobj(-15)
            body = inflater.decompress(compressed, item.file_size + 1)
            if not inflater.eof or len(body) > item.file_size:
                raise ValueError("zip_decompression_exceeds_declared_size")
        elif item.compress_type == zipfile.ZIP_STORED:
            body = compressed
        else:
            raise ValueError("unsupported_zip_compression")
        if len(body) != item.file_size or zlib.crc32(body) & 0xFFFFFFFF != item.CRC:
            raise ValueError("zip_member_crc_or_size_mismatch")
        return body, {"archive_file_id": self.file["id"], "member": name, "crc32": f"{item.CRC:08x}",
                      "archive_md5_not_verified_partial_download": True, "sha256": sha(body)}


def sample(fetcher, count=20):
    if not 1 <= count <= 20:
        raise ValueError("first_round_imaging_sample_limit_20_studies")
    metadata, retrieval = fetcher.json("https://api.figshare.com/v2/articles/14825193")
    if metadata["version"] != 2 or metadata["license"]["url"] != "https://creativecommons.org/licenses/by/4.0/":
        raise ValueError("dataset_version_or_license_needs_review")
    write(DATA / "raw/graz/metadata.json", metadata)
    files = {f["name"]: f for f in metadata["files"]}
    raw = DATA / "raw/graz"
    for name in ("dataset.csv", "folder_structure.zip"):
        file = files[name]
        b, _ = fetcher.get(file["download_url"], expected_md5=file["computed_md5"])
        (raw / name).write_bytes(b)
    rows = list(csv.DictReader(io.StringIO((raw / "dataset.csv").read_text(encoding="utf-8-sig"))))
    annotations = zipfile.ZipFile(raw / "folder_structure.zip")
    groups = defaultdict(list)
    for row in rows:
        # timehash is per IMAGE, not a study ID. Keep every view in the selected study.
        groups[(row["patient_id"], row["study_number"])].append(row)
    # Deterministic review sample: earliest listed study of 20 distinct source patients.
    chosen, patients = [], set()
    for key in sorted(groups, key=lambda k: (int(k[0]), int(k[1]))):
        if key[0] not in patients:
            chosen.append(key)
            patients.add(key[0])
        if len(chosen) == count:
            break
    archive = RemoteZip(fetcher, files["images_part1.zip"])
    studies, images = [], []
    class_map = annotations.read("yolov5/meta.yaml").decode("utf-8")
    (raw / "yolov5-meta.yaml").write_text(class_map, encoding="utf-8")
    for patient, study in chosen:
        study_id = f"STUDY_GRAZPEDWRI_DX_V2_P{int(patient):04d}_S{int(study):02d}"
        record = {"study_id": study_id, "dataset_source_id": "SRC_DATASET_GRAZPEDWRI_DX_V2",
                  "original_study_id": {"patient_id": patient, "study_number": study},
                  "patient_group_id": "GRAZPEDWRI_DX:P" + patient,
                  "grouping_basis": "publisher dataset.csv patient_id + study_number; timehash is image-specific",
                  "labels": [], "image_ids": [], "annotation_refs": [],
                  "label_scope": "original image rows retained; no inferred study diagnosis or management answer",
                  "split": "unassigned_review_only", "expert_verified": False}
        for row in groups[(patient, study)]:
            stem = row["filestem"]
            options = [n for n in archive.members if n.rsplit("/", 1)[-1] == stem + ".png"]
            if len(options) != 1:
                raise ValueError("image_missing_or_ambiguous_in_primary_archive")
            body, proof = archive.member(options[0])
            image = Image.open(io.BytesIO(body))
            image.load()
            xml_name = "pascalvoc/" + stem + ".xml"
            xml = annotations.read(xml_name)
            annotation = ET.fromstring(xml)
            if annotation.findtext("filename").strip() != stem + ".png":
                raise ValueError("annotation_image_filename_mismatch")
            width, height = image.size
            objects = []
            for obj in annotation.findall("object"):
                box = {key: int(obj.findtext("bndbox/" + key)) for key in ("xmin", "ymin", "xmax", "ymax")}
                if not (0 <= box["xmin"] <= box["xmax"] <= width and 0 <= box["ymin"] <= box["ymax"] <= height):
                    raise ValueError("annotation_outside_image")
                objects.append({"name": obj.findtext("name").strip(), "bbox_original": box})
            image_id = "IMG_GRAZ_V2_" + stem
            path = DATA / "images/dataset" / (stem + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            annotation_path = DATA / "processed/annotations" / (stem + ".xml")
            annotation_path.parent.mkdir(parents=True, exist_ok=True)
            annotation_path.write_bytes(xml)
            yolo_name = "yolov5/labels/" + stem + ".txt"
            yolo = annotations.read(yolo_name)
            yolo_path = annotation_path.with_suffix(".txt")
            yolo_path.write_bytes(yolo)
            # Preserve VOC coordinates as published. Do not silently shift 0/1-based origin.
            image_record = {"image_id": image_id, "case_id": None, "study_id": study_id,
                            "modality": "XR", "body_region": "pediatric wrist", "view": None,
                            "view_source_code": row["projection"], "local_path": path.relative_to(DATA).as_posix(),
                            "original_url": files["images_part1.zip"]["download_url"],
                            "caption": None, "source_id": "SRC_DATASET_GRAZPEDWRI_DX_V2", "sha256": sha(body),
                            "width": width, "height": height, "annotation_refs": [annotation_path.relative_to(DATA).as_posix(), yolo_path.relative_to(DATA).as_posix()],
                            "annotations": objects, "annotation_coordinate_system": "published Pascal VOC xyxy in pixels; origin not reinterpreted",
                            "source_row": row, "archive_member": proof,
                            "privacy_review": "pending_visual_review_text_annotations_present" if any(o["name"] == "text" for o in objects) else "pending_visual_review",
                            "diagnosis_leakage_review": "annotations and metadata may disclose findings; not an authored exercise",
                            "expert_verified": False}
            images.append(image_record)
            record["image_ids"].append(image_id)
            record["labels"].append({"image_id": image_id, "original_row": row})
            record["annotation_refs"].extend(image_record["annotation_refs"])
        studies.append(record)
        write(DATA / "processed/imaging-studies.json", studies)
        write(DATA / "processed/dataset-images.json", images)
        print("Dataset study completed:", study_id, len(record["image_ids"]), "images", flush=True)
    source = {"source_id": "SRC_DATASET_GRAZPEDWRI_DX_V2", "data_kind": "labeled_imaging_dataset",
              "title": metadata["title"], "authors": [a["full_name"] for a in metadata["authors"]],
              "year": 2022, "doi": metadata["doi"], "dataset_version": metadata["version"],
              "original_url": metadata["url_public_html"], "license": "CC BY 4.0", "license_url": metadata["license"]["url"],
              "attribution_text": "; ".join(a["full_name"] for a in metadata["authors"]) + ". GRAZPEDWRI-DX v2. " + metadata["doi"] + ". CC BY 4.0. Selective unmodified sample.",
              "retrieval_date": retrieval["retrieval_date"], "access": "public_no_login",
              "rights": {"download": True, "automated_download": True, "store_images": True, "adapt": True, "redistribute": True, "attribution_required": True, "noncommercial_only": False},
              "label_limitations": "Annotations may be incomplete or imperfect; no full clinical history, treatment, outcome or teaching answer key.",
              "archive_sizes": {n: f["size"] for n, f in files.items()},
              "sample_method": "first study of first 20 distinct numeric patient IDs; not representative or balanced",
              "source_documentation": ["https://www.nature.com/articles/s41597-022-01328-z", "raw/graz/yolov5-meta.yaml"]}
    write(DATA / "catalog/graz-source.json", source)
    return studies, images
