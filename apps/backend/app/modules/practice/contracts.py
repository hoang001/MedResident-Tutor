# ruff: noqa: E402
"""CPU-only validators/guards shared with pilots; no dataset is loaded here."""

import sys
from pathlib import Path

for parent in Path(__file__).resolve().parents:
    if (parent / "model-training").is_dir():
        sys.path.insert(0, str(parent / "model-training"))
        break
# Packaged Docker deployment supplies /opt/pilot through PYTHONPATH.

from src.medical.validation import (  # noqa: E402
    EvaluationRequest as EvaluationRequest,
)
from src.medical.validation import (
    ServiceError as ServiceError,
)
from src.medical.validation import (
    strict_json as strict_json,
)
from src.medical.validation import (
    validate_output as validate_output,
)
from src.teaching.apply_teaching_guards import apply_teaching_guards  # noqa: E402
from src.teaching.validate_dataset import (  # noqa: E402
    contract_errors,
    input_errors,
    prediction_metrics,
)


def validate_teaching(payload, prediction):
    if input_errors(payload):
        raise ServiceError("TEACHING_INPUT_INVALID", 502)
    if contract_errors(prediction):
        raise ServiceError("TEACHING_SCHEMA_INVALID", 502)
    guarded = apply_teaching_guards(payload, prediction)
    metrics, errors = prediction_metrics(payload, guarded)
    if errors or not all(metrics.values()):
        raise ServiceError("TEACHING_ALIGNMENT_INVALID", 502)
    return guarded
