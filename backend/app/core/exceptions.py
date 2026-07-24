from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApplicationError(Exception):
    """Base class for all application/domain errors."""


class NotFoundError(ApplicationError):
    """A referenced resource does not exist."""


class ConflictError(ApplicationError):
    """The request conflicts with the current state of a resource (e.g. a duplicate)."""


class ValidationError(ApplicationError):
    """The request violates a domain-level validation rule."""


class BusinessRuleError(ApplicationError):
    """The request is well-formed but violates a business rule."""


class AuthenticationError(ApplicationError):
    """The request lacks valid authentication credentials."""


class PermissionDeniedError(ApplicationError):
    """The request is authenticated but not authorized to perform this action."""


_STATUS_CODES: dict[type[ApplicationError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ValidationError: 422,
    BusinessRuleError: 422,
    AuthenticationError: 401,
    PermissionDeniedError: 403,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Register one handler per ApplicationError subclass in _STATUS_CODES.

    Starlette resolves handlers by walking the raised exception's MRO, so a
    domain exception such as OwnerNotFoundError(NotFoundError) is caught here
    automatically — entities never need to register their own handlers.
    """
    for error_cls, status_code in _STATUS_CODES.items():

        async def _handler(
            request: Request, exc: ApplicationError, status_code: int = status_code
        ) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})

        app.add_exception_handler(error_cls, _handler)
