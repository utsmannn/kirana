import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class KiranaException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        type: str = "invalid_request_error",
        status_code: int = 400,
        param: Optional[str] = None
    ):
        self.code = code
        self.message = message
        self.type = type
        self.status_code = status_code
        self.param = param

async def kirana_exception_handler(request: Request, exc: KiranaException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "type": exc.type,
                "param": exc.param
            }
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "error",
                "message": exc.detail,
                "type": "api_error",
                "param": None
            }
        }
    )

async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred. Please try again later.",
                "type": "api_error",
                "param": None
            }
        }
    )
