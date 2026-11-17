"""CPU-only transport/contract regression checks; never contacts RunPod."""
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOCKER="C:/Program Files/Docker/Docker/resources/bin/docker.exe"


def main():
    target=ROOT/"data/authoring/runpod-config-20261112"
    target.mkdir(parents=True,exist_ok=True)
    cmd=[DOCKER,"run","--rm","--mount",f"type=bind,source={ROOT},target=/workspace",
        "-w","/workspace/apps/backend","-e","PYTHONPATH=/workspace/apps/backend:/workspace/model-training:/tmp/checkdeps",
        "medresident-tutor-backend:latest","sh","-c",
        "pip install -q --target /tmp/checkdeps pytest pytest-asyncio aiosqlite numpy ruff && "
        "PYTHONPATH=/tmp/checkdeps python -m ruff format app/ai/remote_chat.py app/core/config.py app/modules/practice/providers.py app/modules/practice/router.py app/modules/questions/authoring.py tests/test_remote_models.py && "
        "PYTHONPATH=/tmp/checkdeps python -m ruff check app/ai/remote_chat.py app/core/config.py app/modules/practice/providers.py app/modules/practice/router.py app/modules/questions/authoring.py tests/test_remote_models.py --fix && "
        "python -m pytest -q tests/test_remote_models.py tests/test_authoring.py tests/test_practice_contracts.py tests/test_practice_retrieval.py tests/test_structured_practice.py --junitxml=/workspace/data/authoring/runpod-config-20261112/results.xml"]
    p=subprocess.run(cmd,capture_output=True)
    out=(p.stdout+p.stderr).decode('utf-8',errors='replace')
    (target/'tests.log').write_text(out,encoding='utf-8')
    print(out[-6000:].encode('ascii','backslashreplace').decode())
    raise SystemExit(p.returncode)


if __name__=='__main__':main()
