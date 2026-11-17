"""Safe diagnostics: phases/check names only, never payloads or generated text."""

from .validation import ServiceError


class DiagnosticServiceError(ServiceError):
    def __init__(self, code, status, *, phase, failed_checks=(), error_type=None):
        super().__init__(code, status)
        self.phase = phase
        self.failed_checks = tuple(failed_checks)
        self.error_type = error_type
