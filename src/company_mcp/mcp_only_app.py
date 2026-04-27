from fastapi import FastAPI

from company_mcp.config import settings
from company_mcp.mcp.server import mcp

mcp_app = mcp.http_app()
app = FastAPI(
    title=f"{settings.app_name}-mcp",
    version=settings.app_version,
    lifespan=mcp_app.lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", mcp_app)
