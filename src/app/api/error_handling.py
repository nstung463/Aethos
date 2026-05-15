from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.logger import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def ensure_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        return request_id
    header_request_id = request.headers.get(REQUEST_ID_HEADER, "").strip()
    request_id = header_request_id or uuid.uuid4().hex
    request.state.request_id = request_id
    return request_id


def error_payload(
    *,
    request: Request,
    detail: Any,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"detail": detail, "request_id": ensure_request_id(request)}
    if extras:
        payload.update(extras)
    return payload


def _request_log_fields(request: Request) -> dict[str, Any]:
    return {
        "request_id": ensure_request_id(request),
        "method": request.method,
        "path": request.url.path,
        "query": request.url.query,
        "client": request.client.host if request.client else "unknown",
        "user_id": getattr(request.state, "user_id", None),
    }


def _log_http_exception(request: Request, exc: HTTPException) -> None:
    fields = _request_log_fields(request)
    message = (
        "HTTP exception raised "
        "(request_id=%s, method=%s, path=%s, status=%s, user_id=%s, detail=%r)"
    )
    log_args = (
        fields["request_id"],
        fields["method"],
        fields["path"],
        exc.status_code,
        fields["user_id"],
        exc.detail,
    )
    if exc.status_code >= 500:
        logger.error(message, *log_args)
    else:
        logger.warning(message, *log_args)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    _log_http_exception(request, exc)
    payload = error_payload(request=request, detail=exc.detail)
    response = JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers or None)
    response.headers[REQUEST_ID_HEADER] = payload["request_id"]
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = _request_log_fields(request)
    logger.warning(
        "Request validation failed "
        "(request_id=%s, method=%s, path=%s, user_id=%s, errors=%s)",
        fields["request_id"],
        fields["method"],
        fields["path"],
        fields["user_id"],
        exc.errors(),
    )
    payload = error_payload(
        request=request,
        detail="Request validation failed",
        extras={"errors": exc.errors()},
    )
    response = JSONResponse(status_code=422, content=payload)
    response.headers[REQUEST_ID_HEADER] = payload["request_id"]
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    fields = _request_log_fields(request)
    logger.exception(
        "Unhandled API exception "
        "(request_id=%s, method=%s, path=%s, user_id=%s, error_type=%s)",
        fields["request_id"],
        fields["method"],
        fields["path"],
        fields["user_id"],
        exc.__class__.__name__,
    )
    payload = error_payload(
        request=request,
        detail=f"Internal server error while handling {request.method} {request.url.path}",
        extras={"error_type": exc.__class__.__name__},
    )
    response = JSONResponse(status_code=500, content=payload)
    response.headers[REQUEST_ID_HEADER] = payload["request_id"]
    return response


async def request_tracing_middleware(request: Request, call_next: Any) -> Any:
    request_id = ensure_request_id(request)
    started_at = time.perf_counter()
    logger.info(
        "HTTP request started (request_id=%s, method=%s, path=%s, client=%s)",
        request_id,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    response.headers.setdefault(REQUEST_ID_HEADER, request_id)
    logger.info(
        "HTTP request finished (request_id=%s, method=%s, path=%s, status=%s, duration_ms=%.2f)",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

