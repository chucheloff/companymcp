from fastapi import FastAPI

from company_mcp.config import settings
from company_mcp.mcp.server import mcp

mcp_app = mcp.http_app()
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=mcp_app.lifespan,
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# FastMCP already exposes its HTTP transport at /mcp internally.
# Mounting at "/" keeps the public endpoint at exactly /mcp.
app.mount("/", mcp_app)
