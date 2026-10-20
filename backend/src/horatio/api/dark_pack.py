"""Paradox's Dark Pack resources, as this server's operator imported them
(horatio.dark_pack): whether there are any, the Dark Pack logo for the About
page (public, like the page), and the clans' symbols (for anyone signed in)."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from horatio import dark_pack
from horatio.auth.deps import CurrentUser

router = APIRouter(prefix="/dark-pack", tags=["dark pack"])

# The import rewrites these files in place, so browsers check back daily.
CACHE = {"Cache-Control": "public, max-age=86400"}


class DarkPackOut(BaseModel):
    # Whether the Dark Pack logo is here to show (/api/dark-pack/logo.webp).
    logo: bool
    # Clans with a Dark Pack symbol.
    clans: list[str]


@router.get("")
def about_dark_pack() -> DarkPackOut:
    return DarkPackOut(logo=dark_pack.has_logo(), clans=sorted(dark_pack.clan_logos()))


@router.get("/{name}", response_class=FileResponse)
def logo(name: str) -> FileResponse:
    path = dark_pack.logo_file(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No Dark Pack logo here.")
    return FileResponse(path, media_type="image/webp", headers=CACHE)


@router.get("/clans/{clan}/{name}", response_class=FileResponse)
def clan_symbol(clan: str, name: str, user: CurrentUser) -> FileResponse:
    return _symbol(clan, name, white=False)


@router.get("/clans/{clan}/white/{name}", response_class=FileResponse)
def clan_symbol_white(clan: str, name: str, user: CurrentUser) -> FileResponse:
    return _symbol(clan, name, white=True)


def _symbol(clan: str, name: str, *, white: bool) -> FileResponse:
    path = dark_pack.clan_file(clan, name, white)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such symbol.")
    return FileResponse(path, media_type="image/webp", headers=CACHE)
