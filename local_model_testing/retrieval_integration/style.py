"""Format/lint only the changed application files; disposable tool install."""

import os
import subprocess
import sys

from .common import RUN


def main():
    target = "/tmp/retrieval-style-tools"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--target",
            target,
            "ruff==0.12.12",
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    env = {**os.environ, "PYTHONPATH": target + ":" + os.environ.get("PYTHONPATH", "")}
    files = [
        "apps/backend/app/ai/retrieval",
        "apps/backend/app/core/config.py",
        "apps/backend/app/integration/reader.py",
        "apps/backend/app/modules/practice/service.py",
        "apps/backend/app/modules/practice/router.py",
        "apps/backend/app/modules/practice/providers.py",
        "apps/backend/tests/test_practice_retrieval.py",
        "local_model_testing/retrieval_integration",
    ]
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", *files], env=env, check=False
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", *files], env=env, check=True
    )
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *files],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (RUN / "ruff-check.txt").write_text(result.stdout, encoding="utf-8")
    print(result.stdout)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
