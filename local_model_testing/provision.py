"""Fetch only the two named public base snapshots, pin revision and verify each file."""

import argparse
import hashlib
import os
import shutil
import re
import ssl
import time
from pathlib import Path

from .common import KINDS, MODELS, REPORT, file_hash, read, write


def inventory():
    import ssl
    import httpx
    import truststore

    plans = {}
    with httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=40
    ) as client:
        for kind, item in KINDS.items():
            response = client.get(
                "https://huggingface.co/api/models/" + item["repo"] + "?blobs=true"
            )
            response.raise_for_status()
            record = response.json()
            files = [
                f
                for f in record["siblings"]
                if f["rfilename"].endswith((".safetensors", ".json", ".txt", ".model"))
                or f["rfilename"] in {"LICENSE", "README.md"}
            ]
            files = [f for f in files if "/" not in f["rfilename"]]
            plans[kind] = {
                "repo_id": item["repo"],
                "revision": record["sha"],
                "local_path": str(MODELS / "base" / item["name"]),
                "license": record.get("cardData", {}).get("license"),
                "files": files,
                "total_bytes": sum(f.get("size", 0) for f in files),
                "pilot_revision_match": "not_verifiable_without_original_adapter_provenance",
            }
    required = sum(p["total_bytes"] for p in plans.values()) + 15 * 1024**3
    if shutil.disk_usage(MODELS.anchor or Path.cwd().anchor).free < required:
        raise ValueError("insufficient_disk_before_download")
    write(REPORT / "download-plan.json", plans)
    return plans


def download(kind):
    # No token is required for these public repos; do not use saved implicit credentials.
    os.environ.update(
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_HUB_DISABLE_XET="1",
        HF_HOME=str(MODELS / "hf-cache"),
    )
    import truststore
    import httpx

    plans = read(REPORT / "download-plan.json")
    plan = plans[kind]
    records = []
    for entry in plan["files"]:
        path = Path(plan["local_path"]) / entry["rfilename"]
        valid = False
        if path.is_file() and path.stat().st_size == entry["size"]:
            if entry.get("lfs"):
                valid = file_hash(path) == entry["lfs"]["sha256"]
            else:
                body = path.read_bytes()
                valid = (
                    hashlib.sha1(
                        b"blob " + str(len(body)).encode() + b"\0" + body
                    ).hexdigest()
                    == entry["blobId"]
                )
        if not valid:
            path.parent.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix(path.suffix + ".part")
            offset = part.stat().st_size if part.exists() else 0
            url = (
                "https://huggingface.co/"
                + plan["repo_id"]
                + "/resolve/"
                + plan["revision"]
                + "/"
                + entry["rfilename"]
            )
            last_progress = time.monotonic()
            with httpx.Client(
                verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                timeout=httpx.Timeout(60, connect=30),
                follow_redirects=True,
            ) as client:
                with client.stream(
                    "GET", url, headers={"Range": f"bytes={offset}-"} if offset else {}
                ) as response:
                    if response.status_code not in (200, 206):
                        # Never print signed redirect URLs or credentials in exception output.
                        raise RuntimeError(f"download_http_{response.status_code}")
                    if response.status_code == 206:
                        match = re.fullmatch(
                            r"bytes (\d+)-(\d+)/(\d+)",
                            response.headers.get("content-range", ""),
                        )
                        if (
                            not match
                            or int(match[1]) != offset
                            or int(match[3]) != entry["size"]
                        ):
                            raise ValueError("download_range_mismatch")
                    else:
                        offset = 0
                    with part.open("ab" if offset else "wb") as stream:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            stream.write(chunk)
                            offset += len(chunk)
                            if offset > entry["size"]:
                                raise ValueError("download_exceeds_expected_size")
                            if time.monotonic() - last_progress >= 30:
                                print(
                                    kind,
                                    entry["rfilename"],
                                    f"{offset}/{entry['size']} bytes",
                                    flush=True,
                                )
                                last_progress = time.monotonic()
            if part.stat().st_size != entry["size"]:
                raise ValueError("download_incomplete")
            part.replace(path)
        actual = file_hash(path)
        if path.stat().st_size != entry["size"] or (
            entry.get("lfs") and actual != entry["lfs"]["sha256"]
        ):
            raise ValueError("downloaded_file_hash_or_size_mismatch")
        if not entry.get("lfs"):
            b = path.read_bytes()
            if (
                hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
                != entry["blobId"]
            ):
                raise ValueError("downloaded_git_blob_mismatch")
        records.append(
            {
                "file": entry["rfilename"],
                "size": path.stat().st_size,
                "sha256": actual,
                "reused_verified_file": valid,
            }
        )
        write(
            REPORT / (kind + "-download.json"),
            {
                **{k: v for k, v in plan.items() if k != "files"},
                "files": records,
                "complete": len(records) == len(plan["files"]),
            },
        )
        print(kind, entry["rfilename"], "verified", path.stat().st_size, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inventory", "medical", "teaching"])
    args = parser.parse_args()
    if args.action == "inventory":
        print(
            {
                k: {"bytes": v["total_bytes"], "revision": v["revision"]}
                for k, v in inventory().items()
            }
        )
    else:
        download(args.action)
