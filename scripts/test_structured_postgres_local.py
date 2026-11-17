"""Run practice regression in one disposable DB; credentials stay in process memory."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
DB = "medresident_test_structured_20261110"


def main():
    sys.path.insert(0, str(ROOT / "apps/backend"))
    from sqlalchemy.engine import make_url

    subprocess.run([DOCKER, "exec", "medresident-tutor-db-1", "sh", "-c",
                    'exec createdb -U "$POSTGRES_USER" ' + DB], check=True, capture_output=True)
    try:
        # stdout is captured and never forwarded to the terminal or an artifact.
        raw = subprocess.check_output([DOCKER, "exec", "medresident-tutor-backend-1", "python",
            "-c", "from app.core.config import get_settings; print(get_settings().database_url)"])
        url = make_url(raw.decode().strip()).set(host="127.0.0.1", port=5433, database=DB)
        env = dict(os.environ, DEBUG="false", PYTHONPATH=str(ROOT / "apps/backend"),
                   INTEGRATION_TEST_DATABASE_URL=url.render_as_string(hide_password=False))
        report = ROOT / "data/clinical-cases/exercises/structured/audit"
        report.mkdir(parents=True, exist_ok=True)
        result = subprocess.run([sys.executable, "-m", "pytest",
            "apps/backend/postgres_tests/test_structured_practice.py",
            "apps/backend/postgres_tests/test_practice.py", "-q",
            "apps/backend/postgres_tests/test_migrations.py",
            "--junitxml=" + str(report / "postgres-tests.xml")], cwd=ROOT, env=env)
    finally:
        subprocess.run([DOCKER, "exec", "medresident-tutor-db-1", "sh", "-c",
                        'exec dropdb -U "$POSTGRES_USER" ' + DB], check=True, capture_output=True)
    print(json.dumps({"disposable_database_removed": True, "exit_code": result.returncode}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
