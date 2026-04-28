"""Middleware setup for the Atrium FastAPI application."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atrium.core.errors import AtriumError


def setup_middleware(app: FastAPI) -> None:
    """Configure CORS and global error handling for the app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AtriumError)
    async def atrium_error_handler(request: Request, exc: AtriumError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_response().model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": str(exc),
                "type": type(exc).__name__,
            },
        )
