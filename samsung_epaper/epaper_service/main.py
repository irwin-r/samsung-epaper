"""Uvicorn entry point for the Samsung ePaper service."""

import logging

import uvicorn

from .api import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "epaper_service.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
