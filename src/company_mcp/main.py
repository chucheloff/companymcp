import uvicorn

from company_mcp.app import app
from company_mcp.config import settings


def run() -> None:
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
    )


if __name__ == "__main__":
    run()
