"""Server entrypoint that honors SERVICE_HOST and SERVICE_PORT environment variables."""
import os

import uvicorn

from src.main import app


def main() -> None:
    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("SERVICE_PORT", "8000"))
    log_level = os.getenv("UVICORN_LOG_LEVEL", "info")
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
