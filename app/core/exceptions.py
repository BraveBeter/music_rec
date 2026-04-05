"""Global exception handlers - sanitized error responses per security design."""
import logging
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("music_rec")


def register_exception_handlers(app: FastAPI):
    """Register global exception handlers on the app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "msg": exc.detail,
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        # Log the full traceback internally
        logger.error(
            f"Unhandled exception on {request.method} {request.url}: "
            f"{traceback.format_exc()}"
        )
        # Return sanitized response to client
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": "Internal server error",
                "data": None,
            },
        )
