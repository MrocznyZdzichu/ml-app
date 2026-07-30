"""Transport-independent errors raised by application services."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base error with a stable machine code and a user-safe message."""

    default_code = "application_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code


class InvalidRequestError(ApplicationError):
    default_code = "invalid_request"


class AuthenticationError(ApplicationError):
    default_code = "authentication_failed"


class AuthorizationError(ApplicationError):
    default_code = "access_denied"


class ResourceNotFoundError(ApplicationError):
    default_code = "resource_not_found"


class ConflictError(ApplicationError):
    default_code = "resource_conflict"


class ValidationError(ApplicationError):
    default_code = "validation_failed"


class ServiceUnavailableError(ApplicationError):
    default_code = "service_unavailable"
