import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from horatio import delivery
from horatio.api import (
    approvals,
    auth,
    character_log,
    characters,
    connectors,
    creation,
    downtimes,
    house_rules,
    membership,
    notifications,
    npcs,
    printing,
    responses,
    roster,
    rules,
    sheets,
    specializations,
    titles,
    troupes,
)
from horatio.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the delivery worker alongside the API (horatio.delivery)."""
    interval = get_settings().delivery_interval
    worker = asyncio.create_task(delivery.send_forever(interval)) if interval > 0 else None
    yield
    if worker is not None:
        worker.cancel()


app = FastAPI(title="Horatio", lifespan=lifespan)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-Horatio"


@app.middleware("http")
async def require_csrf_header(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Refuse state-changing requests that lack the `X-Horatio` header.

    Sign-in is a cookie, so a page on another site could otherwise make a
    signed-in player's browser send requests here. Browsers will not add a
    custom header to a cross-site request without CORS permission, which this
    API never grants, so requiring one blocks that. SameSite=Lax cookies are a
    second line of defence.
    """
    if request.method not in SAFE_METHODS and CSRF_HEADER not in request.headers:
        return JSONResponse({"detail": f"Missing the {CSRF_HEADER} header."}, status_code=403)
    return await call_next(request)


api = APIRouter(prefix="/api")
for module in (
    auth,
    troupes,
    characters,
    creation,
    sheets,
    membership,
    approvals,
    rules,
    downtimes,
    responses,
    roster,
    character_log,
    printing,
    npcs,
    titles,
    notifications,
    house_rules,
    specializations,
    connectors,
):
    api.include_router(module.router)


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)


def serve_frontend(dist: Path) -> None:
    """Serve the built frontend: its files as they are, and index.html for every
    other path that is not the API, so the app's own routes load on refresh."""
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


_frontend_dist = get_settings().frontend_dist
if _frontend_dist and (Path(_frontend_dist) / "index.html").is_file():
    serve_frontend(Path(_frontend_dist))
