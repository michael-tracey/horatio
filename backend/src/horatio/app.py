import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from horatio import delivery, link_previews, secret_links
from horatio.api import (
    account_merges,
    appearance,
    approvals,
    audit,
    auth,
    backstories,
    backups,
    badges,
    blog,
    blog_authors,
    blog_public,
    blog_tags,
    bond_web,
    bonds,
    book_traits,
    boon_audits,
    boon_export,
    boon_gallant,
    boon_imports,
    boon_reports_told,
    boon_reviews,
    boon_standings,
    boon_statistics,
    boon_status,
    boon_talons,
    boonbreakers,
    boons,
    builds,
    calendar,
    cart,
    character_backup,
    character_log,
    character_moves,
    character_titles,
    characters,
    checkin,
    chronicle,
    clan_logos,
    connectors,
    court,
    creation,
    dark_pack,
    discord,
    discord_account,
    discord_confirm,
    discord_sign_in,
    downtime_effects,
    downtimes,
    email_changes,
    embrace,
    equipment,
    feeding,
    free_changes,
    game_xp,
    games,
    havens,
    house_checks,
    house_rules,
    house_traits,
    in_character,
    influence_charts,
    influence_effects,
    influence_history,
    influence_log,
    influence_lookups,
    jyhad_card,
    keywords,
    lines_veils,
    location_quests,
    locations,
    membership,
    motif_tags,
    nominations,
    notification_settings,
    notifications,
    npc_gifts,
    npcs,
    pictures,
    play,
    play_others,
    players,
    posts,
    power_choices,
    preferences,
    printing,
    projects,
    public_pictures,
    public_troupes,
    quests,
    recent_tabs,
    remembrances,
    responses,
    retainer_rules,
    retainers,
    roster,
    rules,
    scenes,
    search,
    sect_status,
    setting_style,
    setup,
    shared_backgrounds,
    sharing,
    sheets,
    sire_lines,
    site_email,
    site_services,
    specializations,
    story_bible,
    suspensions,
    system,
    targets,
    teachers,
    throttled,
    throw_images,
    titles,
    tools,
    trait_exceptions,
    troupe_equipment,
    troupe_profiles,
    troupe_requests,
    troupe_settings_share,
    troupes,
    two_step,
    unsubscribe,
    viewing,
    vinculum,
    vtes_symbols,
    waiting,
    whos_who,
    written_rules,
    xp_awards,
    xp_plans,
    xp_range,
    yorick_imports,
)
from horatio.auth.deps import DbSession
from horatio.auth.two_step import allowed_first, two_step_first
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


# Sent on every answer (horatio.app.send_security_headers). In production nginx sends
# the same, on its own error pages too (deploy/nginx-horatio.conf.j2).
# - No other site may show Horatio in a frame (issue #1061): a deceptive page laid over
#   it could trick a signed-in player into clicking a real button. Nothing in Horatio
#   frames its own pages; the email design's preview is a sandboxed srcdoc, which
#   these don't touch.
# - No page tells anyone, Horatio included, the address it was opened at (issue
#   #1060): a reset, claim, unsubscribe or calendar link's address is its secret
#   (horatio.secret_links), and the browser would otherwise send it as the Referer of
#   the page's every request.
SECURITY_HEADERS = {
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def send_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add SECURITY_HEADERS to every answer: the app's pages, the API, and its errors.

    Added after the CSRF check, so it wraps it and that refusal carries them too.
    """
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# uvicorn logs every request's path, and production keeps its logs in Cloud Logging.
logging.getLogger("uvicorn.access").addFilter(secret_links.RedactSecrets())


# While the custodian views as someone, nothing changes (horatio.auth.viewing). Someone
# who must set up two-step sign-in does that first (horatio.auth.two_step).
api = APIRouter(
    prefix="/api", dependencies=[Depends(read_only_while_viewing), Depends(two_step_first)]
)
for module in (
    auth,
    troupes,
    troupe_profiles,
    throw_images,
    games,
    checkin,
    game_xp,
    calendar,
    characters,
    clan_logos,
    dark_pack,
    creation,
    sheets,
    power_choices,
    cart,
    xp_plans,
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
    downtime_effects,
    roster,
    builds,
    character_log,
    audit,
    printing,
    pictures,
    public_pictures,
    npcs,
    retainer_rules,
    retainers,
    titles,
    character_titles,
    sect_status,
    notifications,
    notification_settings,
    house_checks,
    house_rules,
    free_changes,
    house_traits,
    book_traits,
    teachers,
    influence_log,
    influence_charts,
    influence_effects,
    influence_history,
    influence_lookups,
    shared_backgrounds,
    sire_lines,
    locations,
    location_quests,
    havens,
    specializations,
    connectors,
    discord,
    discord_account,
    discord_confirm,
    discord_sign_in,
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
    appearance,
    play,
    play_others,
    character_moves,
    npc_gifts,
    in_character,
    account_merges,
    scenes,
    waiting,
    setup,
    viewing,
    whos_who,
    quests,
    backstories,
    setting_style,
    motif_tags,
    site_services,
    site_email,
    written_rules,
    nominations,
    remembrances,
    bonds,
    vinculum,
    bond_web,
    boons,
    boon_audits,
    boon_export,
    boon_gallant,
    boon_reports_told,
    boon_reviews,
    boonbreakers,
    boon_standings,
    boon_statistics,
    boon_status,
    boon_talons,
    court,
    chronicle,
    story_bible,
    recent_tabs,
    posts,
    blog,
    blog_public,
    blog_tags,
    targets,
    projects,
    keywords,
    troupe_settings_share,
    character_backup,
    yorick_imports,
    boon_imports,
    tools,
    throttled,
    two_step,
    vtes_symbols,
    jyhad_card,
    search,
    blog_authors,
    public_troupes,
):
    api.include_router(module.router)
# The signed-in person's choice of throw pictures (#671), beside the troupe's own.
api.include_router(throw_images.mine_router)
api.include_router(setting_style.presets_router)
# A troupe asking two-step sign-in of its staff (#1057), beside its staff.
api.include_router(two_step.troupe_router)


@api.get("/health")
@allowed_first
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api)
# The blog's feeds, the sitemap and robots.txt (#1162), at the site's top level and
# before the frontend's catch-all below.
app.include_router(sharing.router)


def serve_frontend(dist: Path, target: FastAPI = app) -> None:
    """Serve the built frontend: its files as they are, and index.html for every
    other path that is not the API, so the app's own routes load on refresh."""
    # Link previews need absolute addresses, so index.html names the site's.
    public_url = get_settings().public_url.rstrip("/")
    index = (dist / "index.html").read_text().replace("__HORATIO_PUBLIC_URL__", public_url)

    # index.html names the current build's files, so the browser checks for it
    # every time; those files' names change with their contents, so they never
    # need checking again. The rest keep their names from build to build (the
    # service worker, the manifest, the icons), so they are checked every time too.
    fresh = {"Cache-Control": "no-cache"}
    hashed = {"Cache-Control": "public, max-age=31536000, immutable"}

    @target.get("/{path:path}", include_in_schema=False)
    def frontend(path: str, db: DbSession) -> Response:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        # A public page's own link preview (horatio.link_previews).
        preview = link_previews.for_path(db, path)
        if preview is not None:
            return HTMLResponse(
                link_previews.with_preview(index, preview, public_url), headers=fresh
            )
        candidate = (dist / path).resolve()
        if (
            path
            and candidate.is_file()
            and candidate.is_relative_to(dist.resolve())
            and candidate != (dist / "index.html").resolve()
        ):
            return FileResponse(candidate, headers=hashed if path.startswith("assets/") else fresh)
        # A file that is gone (an old build's page, after a deploy) is not an app
        # route: answering with index.html would hand the browser HTML where it
        # asked for a script.
        if path.startswith("assets/") or (path != "index.html" and PurePosixPath(path).suffix):
            raise HTTPException(status_code=404)
        return HTMLResponse(index, headers=fresh)


_frontend_dist = get_settings().frontend_dist
if _frontend_dist and (Path(_frontend_dist) / "index.html").is_file():
    serve_frontend(Path(_frontend_dist))
