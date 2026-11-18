# ruff: noqa: E402
"""Use the same pure authoring contract in the web backend and model service."""

import sys
from pathlib import Path

for parent in Path(__file__).resolve().parents:
    candidate = parent / "services" / "medical"
    if (candidate / "medical_service" / "authoring_contract.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    sys.path.insert(0, "/opt/model-service")

from medical_service.authoring_contract import (  # noqa: E402
    SYSTEM as SYSTEM,
)
from medical_service.authoring_contract import (
    VERSION as VERSION,
)
from medical_service.authoring_contract import (
    Proposal as Proposal,
)
from medical_service.authoring_contract import (
    Scope as Scope,
)
