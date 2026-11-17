"""Run a selected offline reporting task in the existing Linux CPU environment."""

import argparse
import os
import subprocess

from .common import ROOT, RUN
from .control import DOCKER, IMAGE, backend_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "module",
        choices=["offline_analysis", "plots", "reporting", "cpu_checks", "diagnostics"],
    )
    args = parser.parse_args()
    env, network = backend_environment()
    env["CUDA_VISIBLE_DEVICES"] = ""
    cmd = [
        DOCKER,
        "run",
        "--rm",
        "--name",
        "medresident-confirmation-cpu",
        "--label",
        "medresident.retrieval-supplement=" + RUN.name,
        "--network",
        network,
        "--mount",
        "type=bind,source=" + str(ROOT) + ",target=/workspace",
        "--mount",
        "type=volume,source=medresident-local-model-venv,target=/opt/local-models-venv",
        "-w",
        "/workspace",
    ]
    for name in env:
        cmd += ["-e", name]
    cmd += [
        "--entrypoint",
        "/opt/local-models-venv/bin/python",
        IMAGE,
        "-m",
        "local_model_testing.retrieval_confirmation." + args.module,
    ]
    p = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True)
    out = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    for name, value in env.items():
        if value and any(s in name for s in ("PASSWORD", "SECRET", "KEY", "URL")):
            out = out.replace(value, "[REDACTED]")
    (RUN / (args.module + ".log")).write_text(out, encoding="utf-8")
    print(out[-9000:])
    raise SystemExit(p.returncode)


if __name__ == "__main__":
    main()
