"""Error response envelope and exception hierarchy."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class AtriumError(Exception):
    """Base for all Atrium-specific exceptions. Each carries an error_code."""
    error_code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=self.error_code, message=self.message, details=self.details
        )


class ValidationError(AtriumError):
    error_code = "validation_error"
    http_status = 400


class NotFoundError(AtriumError):
    error_code = "not_found"
    http_status = 404


class ConflictError(AtriumError):
    error_code = "conflict"
    http_status = 409


class GuardrailViolation(AtriumError):
    """Raised when a guardrail limit is exceeded.

    Preserved backward-compat with the old ``guardrails.GuardrailViolation``
    which used ``code`` + ``message`` attributes.
    """
    error_code = "guardrail_violation"
    http_status = 422

    def __init__(
        self,
        code_or_message: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        # Support both calling conventions:
        #   GuardrailViolation("MAX_TIME", "elapsed 10s exceeds ...")   (old)
        #   GuardrailViolation("elapsed 10s exceeds ...", details={})   (new)
        if message is not None:
            # old-style: code_or_message is the code
            self.code = code_or_message
            actual_message = message
        else:
            # new-style: code_or_message is the message
            self.code = self.error_code
            actual_message = code_or_message
        super().__init__(actual_message, details)

    def __str__(self) -> str:
        # Preserve backward-compat: str(exc) == "CODE: message"
        return f"{self.code}: {self.message}"
