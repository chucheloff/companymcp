import uvicorn

from company_mcp.config import settings
from company_mcp.mcp_only_app import app


def run() -> None:
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.mcp_port,
    )


if __name__ == "__main__":
    run()
