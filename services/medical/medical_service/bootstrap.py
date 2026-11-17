"""CPU-only artifact preflight followed by the single two-model Uvicorn process."""

import argparse
import json
import os
import sys
from pathlib import Path

from .config import Settings, TeachingSettings, shared_api_key_variable
from .processes import ensure_port_available
from .runner import check_artifacts, sha256
from .teaching import TeachingRunner
from .validation import ServiceError


def deployment_hashes():
    """Inventory local files only; computing hashes alone does not establish V1 provenance."""
    result = {}
    for prefix in ("MEDICAL", "TEACHING"):
        try:
            base = Path(os.environ[prefix + "_BASE_MODEL_PATH"])
            adapter = Path(os.environ[prefix + "_ADAPTER_PATH"])
        except KeyError:
            raise ServiceError(prefix + "_PATH_NOT_CONFIGURED", 503) from None
        for suffix, path in (
            ("ADAPTER_SHA256", adapter / "adapter_model.safetensors"),
            ("BASE_CONFIG_SHA256", base / "config.json"),
            ("ADAPTER_CONFIG_SHA256", adapter / "adapter_config.json"),
        ):
            try:
                result[prefix + "_" + suffix] = sha256(path)
            except OSError:
                raise ServiceError(prefix + "_ARTIFACT_FILE_UNREADABLE", 503) from None
    return result


def verify_deployment():
    actual = deployment_hashes()
    computed = set()
    for name, value in actual.items():
        if not os.environ.get(name, "").strip():
            os.environ[name] = value
            computed.add(name)
    key_variable = shared_api_key_variable()
    for name, config, check in (
        ("MEDICAL", Settings, check_artifacts),
        ("TEACHING", TeachingSettings, lambda settings: TeachingRunner(settings)._check()),
    ):
        try:
            settings = config.from_env(api_key_variable=key_variable)
            metadata = check(settings)
        except ServiceError as exc:
            raise ServiceError(name + "_" + exc.code, 503) from None
        except ValueError:
            # Settings errors must not print a secret environment or traceback.
            raise ServiceError(name + "_CONFIGURATION_INVALID", 503) from None
        print(
            json.dumps(
                {
                    "stage": name,
                    "status": "ARTIFACTS_VERIFIED",
                    "model_id": metadata["model_id"],
                    "hash_mode": "computed"
                    if any(k.startswith(name + "_") for k in computed)
                    else "provided",
                    **{
                        k: metadata[k]
                        for k in ("adapter_sha256", "base_config_sha256", "adapter_config_sha256")
                    },
                }
            ),
            flush=True,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--print-hashes",
        action="store_true",
        help="Print local SHA-256 inventory; no GPU/key required",
    )
    mode.add_argument(
        "--check-only", action="store_true", help="Verify both artifact sets without loading a GPU"
    )
    args = parser.parse_args(argv)
    try:
        if args.print_hashes:
            for name, value in deployment_hashes().items():
                print(f"{name}={value}", flush=True)
            return 0
        verify_deployment()
        # Artifact/key validation must succeed before stopping the healthy old service.
        if not args.check_only:
            ensure_port_available()
    except ServiceError as exc:
        print(json.dumps({"error": {"code": exc.code}}), file=sys.stderr, flush=True)
        return 1
    except Exception:
        print(
            json.dumps({"error": {"code": "ARTIFACT_PREFLIGHT_FAILED"}}),
            file=sys.stderr,
            flush=True,
        )
        return 1
    if args.check_only:
        return 0
    # Replace this process. No second GPU worker, port or service is launched.
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "medical_service.unified:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--workers",
            "1",
            "--no-access-log",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
