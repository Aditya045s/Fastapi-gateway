from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(
                    request.state,
                    "request_id",
                    None,
                ),
            }
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return error_response(
        request,
        422,
        "VALIDATION_ERROR",
        "Request validation failed",
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    detail = exc.detail

    if isinstance(detail, dict):
        code = detail.get("code", "HTTP_ERROR")
        message = detail.get("message", "Request failed")
    else:
        code = "HTTP_ERROR"
        message = str(detail)

    return error_response(
        request,
        exc.status_code,
        code,
        message,
    )