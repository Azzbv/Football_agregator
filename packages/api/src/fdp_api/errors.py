"""RFC 9457 problem+json error handling.

A single set of exception handlers turns domain exceptions and validation errors
into ``application/problem+json`` responses with a consistent shape, so every
error the API emits looks the same to clients.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fdp_shared.exceptions import FdpError, NotFoundError, ValidationFailedError
from fdp_shared.logging import get_logger

logger = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"


class Problem(BaseModel):
    """RFC 9457 problem detail object."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


def _problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type=PROBLEM_CONTENT_TYPE,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach problem+json handlers for the platform's error taxonomy."""

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return _problem_response(
            Problem(title="Not Found", status=404, detail=str(exc), instance=str(request.url))
        )

    @app.exception_handler(ValidationFailedError)
    async def _validation_failed(
        request: Request, exc: ValidationFailedError
    ) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Unprocessable Entity",
                status=422,
                detail=str(exc),
                instance=str(request.url),
            )
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            Problem(
                title="Bad Request",
                status=400,
                detail="; ".join(e["msg"] for e in exc.errors()),
                instance=str(request.url),
            )
        )

    @app.exception_handler(FdpError)
    async def _domain_error(request: Request, exc: FdpError) -> JSONResponse:
        logger.error("unhandled_domain_error", error=str(exc))
        return _problem_response(
            Problem(
                title="Internal Server Error",
                status=500,
                detail=str(exc),
                instance=str(request.url),
            )
        )
