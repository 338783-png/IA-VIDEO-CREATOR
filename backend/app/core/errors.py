import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("errors")


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "app_error"):
        self.message, self.status_code, self.code = message, status_code, code
        super().__init__(message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        log.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.message})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Erreur non gérée sur %s", request.url.path)
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "Erreur interne, voir logs/backend.log"})
