"""Focused CPU regression checks, not the locked model benchmark."""

import os
import subprocess
import sys
from .common import RUN


def main():
    destination = "/tmp/confirmation-test-deps"
    installed = subprocess.run(
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
        ],
        capture_output=True,
    )
    assert installed.returncode == 0, "Disposable CPU test dependencies unavailable"
    env = {
        **os.environ,
        "PYTHONPATH": destination + ":" + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "local_model_testing/retrieval_confirmation/tests",
            "apps/backend/tests/test_practice_retrieval.py",
            "-c",
            "apps/backend/pyproject.toml",
            "-q",
            "--junitxml=" + str(RUN / "software-tests.xml"),
        ],
        env=env,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
