from fastapi import FastAPI

from company_mcp.config import settings
from company_mcp.mcp.server import mcp

app = FastAPI(title=f"{settings.app_name}-mcp", version=settings.app_version)
app.mount("/", mcp.http_app())


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
