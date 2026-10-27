import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.v1.router import router as api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    try:
        request_id = str(uuid.UUID(request.headers.get("X-Request-ID", "")))
    except ValueError:
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception as exc:
        # Handle here too: do not let Uvicorn log a raw exception/request payload.
        response = await unexpected_error_handler(request, exc)
    response.headers["X-Request-ID"] = request_id
    return response


def error_payload(request: Request, code: str, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, exc.code, exc.message, exc.details),
        headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Never serialize input, ctx (which can contain an exception), or raw messages.
    details = []
    for item in exc.errors():
        kind = item.get("type", "invalid")
        message = {
            "missing": "Field required",
            "string_too_short": "Value is too short",
            "string_too_long": "Value is too long",
            "json_invalid": "Invalid JSON",
            "extra_forbidden": "Unexpected field",
        }.get(kind, "Invalid value")
        details.append({"loc": item.get("loc", ()), "type": kind, "msg": message})
    return JSONResponse(
        status_code=422,
        content=error_payload(request, "VALIDATION_ERROR", "Request validation failed", details),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = message if re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", message) else f"HTTP_{exc.status_code}"
    if exc.status_code >= 500:
        message = "Service unavailable" if exc.status_code == 503 else "Request processing failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(request, code, message),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled request error",
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(request, "INTERNAL_SERVER_ERROR", "An unexpected error occurred"),
    )


app.include_router(api_router, prefix=settings.api_v1_prefix)
