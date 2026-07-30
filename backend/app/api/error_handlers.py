"""HTTP adapter for application-layer errors."""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.errors import (
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    InvalidRequestError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


_STATUS_BY_ERROR: tuple[tuple[type[ApplicationError], int], ...] = (
    (InvalidRequestError, status.HTTP_400_BAD_REQUEST),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (AuthorizationError, status.HTTP_403_FORBIDDEN),
    (ResourceNotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (ServiceUnavailableError, status.HTTP_503_SERVICE_UNAVAILABLE),
)


async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
    status_code = next(
        (
            candidate_status
            for error_type, candidate_status in _STATUS_BY_ERROR
            if isinstance(exc, error_type)
        ),
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": exc.message, "code": exc.code},
    )
