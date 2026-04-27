from fastapi import FastAPI

from company_mcp.config import settings
from company_mcp.mcp.server import mcp

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.mount(settings.mcp_path, mcp.http_app())


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
