"""FastAPI entrypoint for the ONVIF reference service."""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from src.discovery import WSDiscoveryResponder
from src.routers import device, events, media, ptz, recording, users

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    service_host = os.getenv("SERVICE_HOST", "0.0.0.0")
    service_port = int(os.getenv("SERVICE_PORT", "8000"))
    discovery_address = f"http://{service_host}:{service_port}/"

    responder = WSDiscoveryResponder(discovery_address)
    logger.info("Starting WS-Discovery responder on %s", discovery_address)
    responder.start()
    try:
        yield
    finally:
        logger.info("Stopping WS-Discovery responder")
        responder.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="ONVIF Reference NVR", lifespan=lifespan)
    app.include_router(device.router)
    app.include_router(media.router)
    app.include_router(events.router)
    app.include_router(recording.router)
    app.include_router(ptz.router)
    app.include_router(users.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICE_PORT", "8000"))
    uvicorn.run("src.main:app", host=host, port=port, reload=False)

