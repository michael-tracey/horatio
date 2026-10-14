from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from horatio.api import auth, characters, troupes

app = FastAPI(title="Horatio")

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


app.include_router(auth.router)
app.include_router(troupes.router)
app.include_router(characters.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
