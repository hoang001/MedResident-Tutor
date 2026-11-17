"""One explicitly authorized run; no automatic inference retry or budget reset."""

import argparse
import os
import subprocess
import sys
import time

from .common import ROOT, RUN, system_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-ram-seconds", type=int, default=0)
    args = parser.parse_args()
    if (RUN / "live.json").exists() or (RUN / "closed.json").exists():
        print("Confirmation run closed; reporting only, no further inference")
        return
    deps = ROOT / "data/evaluation/runs/retrieval-integration-20261111/controller-deps"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(deps))
    import httpx  # noqa: F401 -- resolve before any model container startup

    deadline = time.monotonic() + max(0, args.wait_ram_seconds)
    while True:
        available = system_snapshot()["system"]["ram_available_bytes"] / 1024**3
        if available >= 6:
            break
        print(f"Host RAM {available:.2f}/6.00 GiB; no model startup", flush=True)
        if time.monotonic() >= deadline:
            raise SystemExit("Memory guard retained; finish offline reporting first")
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(deps) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_model_testing.retrieval_confirmation.control",
            "run",
        ],
        env=env,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
