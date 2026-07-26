"""Public exception hierarchy for the ML App client."""

class ApiError(RuntimeError):
    """The platform rejected a request or returned an invalid response."""


class AuthenticationError(ApiError):
    """Authentication credentials are missing or invalid."""


class AuthorizationError(ApiError):
    """The authenticated user lacks access required for an operation."""


class ConflictError(ApiError):
    """The requested mutation conflicts with an existing platform resource."""


class ResourceNotFoundError(ApiError):
    """A named platform resource could not be found."""


class ResourceAmbiguousError(ApiError):
    """A name resolved to more than one platform resource."""
