"""The VTES symbols this server's custodian fetched from KRCG (horatio.vtes_symbols),
for anyone signed in. Characters' Jyhad cards show them; wherever something does, it credits
KRCG and gives Paradox's notice."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from horatio import vtes_symbols
from horatio.api.dark_pack import CACHE
from horatio.auth.deps import CurrentUser

router = APIRouter(prefix="/vtes-symbols", tags=["dark pack"])

# An SVG opened on its own runs nothing and loads nothing.
SVG = {**CACHE, "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"}


@router.get("/fonts/{name}", response_class=FileResponse)
def font(name: str, user: CurrentUser) -> FileResponse:
    path = vtes_symbols.font_file(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such font.")
    media = vtes_symbols.FONT_TYPES[name.rpartition(".")[2]]
    return FileResponse(path, media_type=media, headers=CACHE)


@router.get("/logos/{name}", response_class=FileResponse)
def logo(name: str, user: CurrentUser) -> FileResponse:
    """KRCG's logos: VTES's (`vtes.svg`) and the Dark Pack's (`dark-pack.png`)."""
    path = vtes_symbols.logo_file(name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such logo.")
    suffix = name.rpartition(".")[2]
    return FileResponse(
        path, media_type=vtes_symbols.MEDIA_TYPES[suffix], headers=SVG if suffix == "svg" else CACHE
    )


@router.get("/{kind}/{path:path}", response_class=FileResponse)
def symbol(kind: str, path: str, user: CurrentUser) -> FileResponse:
    """A symbol, as `/api/vtes-symbols/svg/disc/inf/aus.svg`, or white-bordered as
    `/api/vtes-symbols/webp_wb/disc/sup/aus.webp`."""
    found = vtes_symbols.symbol_file(kind, path)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such symbol.")
    return FileResponse(
        found, media_type=vtes_symbols.media_type(kind), headers=SVG if kind == "svg" else CACHE
    )
