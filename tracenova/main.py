"""TraceNova application entry point."""

import uvicorn

from backend.app import create_app
from backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(create_app(), host=settings.host, port=settings.port, access_log=False)


if __name__ == "__main__":
    main()
