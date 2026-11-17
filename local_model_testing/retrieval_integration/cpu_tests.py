"""Disposable CPU test dependencies; never edits the shared inference environment."""

import os
import subprocess
import sys

from .common import RUN


def main():
    destination = "/tmp/retrieval-test-deps"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--target",
            destination,
            "pytest-asyncio==1.1.0",
            "aiosqlite==0.21.0",
            "ruff==0.12.12",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (RUN / "test-dependency-install.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise SystemExit(
            "Disposable test dependencies unavailable; inference venv unchanged"
        )
    env = {
        **os.environ,
        "PYTHONPATH": destination + ":" + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "apps/backend/tests",
            "local_model_testing/retrieval_integration/tests",
            "-c",
            "apps/backend/pyproject.toml",
            "-q",
            "--junitxml=" + str(RUN / "backend-tests.xml"),
        ],
        env=env,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
