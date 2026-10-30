import asyncio
import html
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from horatio import delivery
from horatio.api import (
    account_merges,
    approvals,
    audit,
    auth,
    backups,
    badges,
    cart,
    character_log,
    character_moves,
    characters,
    clan_logos,
    connectors,
    creation,
    dark_pack,
    discord,
    downtimes,
    email_changes,
    embrace,
    equipment,
    feeding,
    house_rules,
    house_traits,
    influence_effects,
    influence_history,
    influence_log,
    influence_lookups,
    lines_veils,
    locations,
    membership,
    notifications,
    npcs,
    pictures,
    play,
    play_others,
    players,
    power_choices,
    preferences,
    printing,
    responses,
    retainers,
    roster,
    rules,
    scenes,
    sect_status,
    shared_backgrounds,
    sheets,
    specializations,
    suspensions,
    system,
    titles,
    trait_exceptions,
    troupe_equipment,
    troupe_profiles,
    troupe_requests,
    troupes,
    unsubscribe,
    viewing,
    waiting,
    whos_who,
    xp_awards,
    xp_range,
)
from horatio.auth.deps import DbSession
from horatio.auth.viewing import read_only_while_viewing
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


# While the custodian views as someone, nothing changes (horatio.auth.viewing).
api = APIRouter(prefix="/api", dependencies=[Depends(read_only_while_viewing)])
for module in (
    auth,
    troupes,
    troupe_profiles,
    characters,
    clan_logos,
    dark_pack,
    creation,
    sheets,
    power_choices,
    cart,
    trait_exceptions,
    embrace,
    membership,
    approvals,
    rules,
    equipment,
    troupe_equipment,
    downtimes,
    feeding,
    responses,
    roster,
    character_log,
    audit,
    printing,
    pictures,
    npcs,
    retainers,
    titles,
    sect_status,
    notifications,
    house_rules,
    house_traits,
    influence_log,
    influence_effects,
    influence_history,
    influence_lookups,
    shared_backgrounds,
    locations,
    specializations,
    connectors,
    discord,
    players,
    lines_veils,
    email_changes,
    suspensions,
    backups,
    badges,
    troupe_requests,
    xp_awards,
    xp_range,
    preferences,
    unsubscribe,
    system,
    play,
    play_others,
    character_moves,
    account_merges,
    scenes,
    waiting,
    viewing,
    whos_who,
):
    api.include_router(module.router)


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)


# A troupe's public profile (horatio.api.troupe_profiles).
PUBLIC_PROFILE = re.compile(r"t/([0-9a-fA-F-]{36})/?")


def with_preview(index: str, preview: dict[str, str], public_url: str) -> str:
    """index.html with its link preview made a troupe's: its name, a line about
    it, and its portrait where it has one (the site's picture where not)."""

    def meta(attribute: str, name: str, value: str, page: str) -> str:
        tag = re.compile(rf'<meta {attribute}="{re.escape(name)}" content="[^"]*" />')
        return tag.sub(
            lambda _: f'<meta {attribute}="{name}" content="{html.escape(value)}" />', page
        )

    page = meta("property", "og:title", preview["title"], index)
    page = meta("property", "og:description", preview["description"], page)
    page = meta("name", "description", preview["description"], page)
    if preview["image"]:
        page = meta("property", "og:image", public_url + preview["image"], page)
        page = meta("property", "og:image:width", "512", page)
        page = meta("property", "og:image:height", "512", page)
        page = meta("name", "twitter:card", "summary", page)
    return page.replace(
        "<title>Horatio</title>", f"<title>{html.escape(preview['title'])} · Horatio</title>"
    )


def serve_frontend(dist: Path, target: FastAPI = app) -> None:
    """Serve the built frontend: its files as they are, and index.html for every
    other path that is not the API, so the app's own routes load on refresh."""
    # Link previews need absolute addresses, so index.html names the site's.
    public_url = get_settings().public_url.rstrip("/")
    index = (dist / "index.html").read_text().replace("__HORATIO_PUBLIC_URL__", public_url)

    # index.html names the current build's files, so the browser checks for it
    # every time; those files' names change with their contents, so they never
    # need checking again.
    fresh = {"Cache-Control": "no-cache"}
    hashed = {"Cache-Control": "public, max-age=31536000, immutable"}

    @target.get("/{path:path}", include_in_schema=False)
    def frontend(path: str, db: DbSession) -> Response:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        public = PUBLIC_PROFILE.fullmatch(path)
        if public:
            try:
                troupe_id = uuid.UUID(public.group(1))
            except ValueError:
                return HTMLResponse(index, headers=fresh)
            preview = troupe_profiles.link_preview(db, troupe_id)
            page = with_preview(index, preview, public_url) if preview else index
            return HTMLResponse(page, headers=fresh)
        candidate = (dist / path).resolve()
        if (
            path
            and candidate.is_file()
            and candidate.is_relative_to(dist.resolve())
            and candidate != (dist / "index.html").resolve()
        ):
            return FileResponse(candidate, headers=hashed if path.startswith("assets/") else None)
        # A file that is gone (an old build's page, after a deploy) is not an app
        # route: answering with index.html would hand the browser HTML where it
        # asked for a script.
        if path.startswith("assets/") or (path != "index.html" and PurePosixPath(path).suffix):
            raise HTTPException(status_code=404)
        return HTMLResponse(index, headers=fresh)


_frontend_dist = get_settings().frontend_dist
if _frontend_dist and (Path(_frontend_dist) / "index.html").is_file():
    serve_frontend(Path(_frontend_dist))
