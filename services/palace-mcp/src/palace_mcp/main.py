import os
from importlib.metadata import version

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def get_version() -> dict[str, str]:
    return {
        "service": "palace-mcp",
        "version": version("palace-mcp"),
        "git_sha": os.environ.get("PALACE_GIT_SHA", "unknown"),
    }
