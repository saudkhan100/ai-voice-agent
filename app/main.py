import sys

from fastapi import FastAPI
from loguru import logger

from app.api import calls, health
from app.config import get_settings


def configure_logging() -> None:
    # diagnose=False: tracebacks must never print variable values (they include API keys).
    logger.remove()
    logger.add(sys.stderr, level="INFO", backtrace=False, diagnose=False)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="Dealer AI", docs_url="/docs" if settings.env == "dev" else None)
    app.include_router(health.router)
    app.include_router(calls.router)
    return app


app = create_app()
