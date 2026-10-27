"""Exclusive publication into the existing upload root, without altering the source."""

import os
import shutil
import tempfile
from pathlib import Path

from app.integration.inputs import CaseConflict, digest, require
from app.storage.local import LocalFileStorage


def publish_pdf(storage: LocalFileStorage, key: str, source: Path, sha256: str) -> bool:
    """Return True only when this invocation published a new destination file.

    A hard link publishes a fully copied temporary file exclusively. Never overwrite
    an existing destination, even if another process wins the publication race.
    """
    target = storage._resolve(key)
    require(target != source.resolve(), "Source and storage destination must differ")
    if target.exists():
        if not target.is_file() or digest(target) != sha256:
            raise CaseConflict("Storage key already exists with different bytes")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".import-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        require(digest(temporary) == sha256, "PDF changed while copying")
        try:
            os.link(temporary, target)
        except FileExistsError:
            if digest(target) != sha256:
                raise CaseConflict("Concurrent storage publication has different bytes") from None
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)
