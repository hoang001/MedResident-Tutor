"""Bounded, sequential official-source retrieval with content-addressed checkpoints."""
import hashlib
import json
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import truststore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/clinical-cases"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_url(url):
    p = urlsplit(url)
    host = p.hostname or ""
    allowed = {"eutils.ncbi.nlm.nih.gov", "pmc-oa-opendata.s3.amazonaws.com", "api.figshare.com",
               "ndownloader.figshare.com", "api.figshare.com", "pmc.ncbi.nlm.nih.gov",
               "www.nature.com", "stanfordmlgroup.github.io", "physionet.org",
               "44c1cec316ec56bca76dfd65d2882b20.r2.cloudflarestorage.com"}
    if (p.scheme != "https" or p.username or p.password or p.port not in (None, 443)
            or not (host in allowed or (host.startswith("figshare") and host.endswith(".amazonaws.com")))):
        raise ValueError("unapproved_source_url")
    return url


class Fetcher:
    def __init__(self, root=DATA, request_limit=300):
        self.root = Path(root)
        self.calls = 0
        self.cache_hits = 0
        self.bytes = 0
        self.request_limit = request_limit
        self.last_request = 0
        self.client = httpx.Client(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), follow_redirects=False,
            timeout=httpx.Timeout(45, connect=10),
            headers={"User-Agent": "MedResident-Tutor-source-review/1.0", "Accept-Encoding": "identity"},
        )

    def get(self, url, *, headers=None, maximum=30_000_000, expected_md5=None):
        safe_url(url)
        headers = headers or {}
        key = sha(json.dumps([url, headers], sort_keys=True).encode())
        folder = self.root / "raw/http"
        meta_path, body_path = folder / (key + ".json"), folder / (key + ".bin")
        if meta_path.exists() and body_path.exists():
            meta, body = read(meta_path), body_path.read_bytes()
            if sha(body) != meta["sha256"]:
                raise ValueError("checkpoint_hash_mismatch")
            if expected_md5 and hashlib.md5(body).hexdigest() != expected_md5:
                raise ValueError("checkpoint_publisher_md5_mismatch")
            self.cache_hits += 1
            return body, meta
        current = url
        for _ in range(6):
            if self.calls >= self.request_limit:
                raise ValueError("request_budget_exhausted")
            time.sleep(max(0, .55 - (time.monotonic() - self.last_request)))
            self.calls += 1
            self.last_request = time.monotonic()
            with self.client.stream("GET", safe_url(current), headers=headers) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = safe_url(urljoin(current, response.headers["location"]))
                    continue
                if "Range" in headers and response.status_code != 206:
                    raise ValueError("range_not_supported_no_full_download")
                response.raise_for_status()
                if int(response.headers.get("content-length", 0)) > maximum:
                    raise ValueError("response_exceeds_byte_budget")
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > maximum:
                        raise ValueError("stream_exceeds_byte_budget")
                    chunks.append(chunk)
                body = b"".join(chunks)
                if expected_md5 and hashlib.md5(body).hexdigest() != expected_md5:
                    raise ValueError("publisher_md5_mismatch")
                meta = {"requested_url": url, "final_host": urlsplit(current).hostname,
                        "request_headers": headers, "status": response.status_code,
                        "content_type": response.headers.get("content-type"),
                        "content_range": response.headers.get("content-range"),
                        "retrieval_date": datetime.now(UTC).isoformat(), "sha256": sha(body), "bytes": len(body),
                        "cache_path": body_path.relative_to(self.root).as_posix()}
                folder.mkdir(parents=True, exist_ok=True)
                body_path.write_bytes(body)
                write(meta_path, meta)
                self.bytes += len(body)
                return body, meta
        raise ValueError("redirect_limit")

    def json(self, url, **kwargs):
        body, meta = self.get(url, **kwargs)
        return json.loads(body), meta
