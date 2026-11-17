"""The GitHub bootstrap is tested with fake git/pip, without any network/GPU."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def tools(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\nfrom pathlib import Path\n"
        "args=sys.argv[1:]\n"
        'with open(os.environ["FAKE_GIT_LOG"],"a") as out: out.write(json.dumps(args)+"\\n")\n'
        'if args[0]=="clone": Path(args[-1],".git").mkdir(parents=True)\n'
        'if "get-url" in args: print(os.environ["FAKE_ORIGIN"])\n'
        'if "--show-current" in args: print(os.environ.get("FAKE_BRANCH","main"))\n'
        'if "rev-parse" in args: print("abc1234")\n'
        'if "diff" in args and os.environ.get("FAKE_DIRTY")=="1": sys.exit(1)\n'
    )
    git.chmod(0o700)
    python = bin_dir / "python fake"
    python.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$FAKE_PIP_LOG"\n')
    python.chmod(0o700)
    checkout = tmp_path / "checkout with spaces"
    env = {
        **os.environ,
        "PATH": str(bin_dir) + ":" + os.environ["PATH"],
        "MODEL_SERVICE_PYTHON": str(python),
        "MEDRESIDENT_REPO_DIR": str(checkout),
        "MEDRESIDENT_REPOSITORY_URL": "https://example.invalid/project.git",
        "MEDRESIDENT_BRANCH": "main",
        "FAKE_ORIGIN": "https://example.invalid/project.git",
        "FAKE_GIT_LOG": str(tmp_path / "git.jsonl"),
        "FAKE_PIP_LOG": str(tmp_path / "pip.txt"),
    }
    return checkout, env


@pytest.mark.parametrize("existing", [False, True])
def test_clone_or_fast_forward_then_install_only_http_package(tools, existing):
    checkout, env = tools
    if existing:
        (checkout / ".git").mkdir(parents=True)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/runpod/bootstrap.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(row) for row in Path(env["FAKE_GIT_LOG"]).read_text().splitlines()]
    if existing:
        assert any("--ff-only" in row for row in calls)
        assert not any("clone" in row for row in calls)
    else:
        assert calls[0][0] == "clone"
    pip = Path(env["FAKE_PIP_LOG"]).read_text().splitlines()
    assert pip == ["-m", "pip", "install", "-e", str(checkout / "services/medical")]
    assert "BOOTSTRAP_READY_NO_INFERENCE_STARTED" in result.stdout
    assert not any("reset" in row or "--hard" in row for row in calls)


@pytest.mark.parametrize("issue", ["dirty", "branch", "origin"])
def test_bootstrap_refuses_to_overwrite_local_state(tools, issue):
    checkout, env = tools
    (checkout / ".git").mkdir(parents=True)
    if issue == "dirty":
        env["FAKE_DIRTY"] = "1"
    elif issue == "branch":
        env["FAKE_BRANCH"] = "other-branch"
    else:
        env["FAKE_ORIGIN"] = "https://example.invalid/other.git"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/runpod/bootstrap.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert not Path(env["FAKE_PIP_LOG"]).exists()
    calls = [json.loads(row) for row in Path(env["FAKE_GIT_LOG"]).read_text().splitlines()]
    assert not any("fetch" in row or "reset" in row or "checkout" in row for row in calls)
