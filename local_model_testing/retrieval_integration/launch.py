"""Check host-only dependencies/RAM before starting the frozen controller once."""

import argparse
import os
import subprocess
import sys
import time

from .common import RUN, system_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-ram-seconds", type=int, default=300)
    args = parser.parse_args()
    if (RUN / "live.json").exists():
        print("Recorded run is closed; no reload, reset, retry or extra inference")
        return
    deps = RUN / "controller-deps"
    if deps.is_dir():
        sys.path.insert(0, str(deps))
    try:
        import httpx  # noqa: F401 -- fail before any Docker model startup
    except ImportError:
        raise SystemExit(
            "Missing host dependency. Run: python -m pip install --target "
            "data/evaluation/runs/retrieval-integration-20261111/controller-deps httpx==0.28.1"
        ) from None
    deadline = time.monotonic() + max(0, args.wait_ram_seconds)
    while True:
        available = system_snapshot()["system"]["ram_available_bytes"] / 1024**3
        if available >= 6:
            break
        print(
            f"Waiting for host RAM: {available:.2f}/6.00 GiB available; no model request",
            flush=True,
        )
        if time.monotonic() >= deadline:
            raise SystemExit("Host RAM guard retained; no model startup requested")
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if deps.is_dir():
        env["PYTHONPATH"] = str(deps) + os.pathsep + env.get("PYTHONPATH", "")
    # Exact existing coordinator command keeps PID/creation-time ownership valid.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_model_testing.retrieval_integration.control",
            "run",
        ],
        env=env,
    )
    # The frozen coordinator may race Docker --rm during exit. This wrapper
    # preserves it and verifies the exact recorded container independently.
    from .owned_cleanup import main as cleanup

    cleanup()
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
