"""Email design on Custodian › Site (#830): the header and footer every email Horatio
sends has (horatio.email_design), a preview, and a test sent to the custodian."""

import uuid
from email.utils import formataddr
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from horatio import email_design, mail_sender, pictures
from horatio.api.site_services import MailTestOut, mail_off, mail_problem
from horatio.audit import record
from horatio.auth.deps import CurrentUser, DbSession
from horatio.connectors import SendError, email
from horatio.email_design import DEFAULTS, Design, DesignError
from horatio.permissions import require_custodian

router = APIRouter(prefix="/site/email-design", tags=["site"])


class HeaderImageOut(BaseModel):
    # Where the card shows it: the API's address for its file.
    url: str
    width: int
    height: int
    # Its size in bytes, as every email carries it.
    size: int


class EmailDesignDefaults(BaseModel):
    site_name: str
    header_colour: str
    header_text_colour: str
    accent: str


class EmailDesignOut(BaseModel):
    # What emails use now: what the custodian set, the defaults for the rest.
    site_name: str
    header_colour: str
    header_text_colour: str
    accent: str
    footer: str
    # Which parts the custodian set; the rest are the defaults.
    chosen: list[str]
    defaults: EmailDesignDefaults
    header_image: HeaderImageOut | None
    # Whether pictures can be uploaded on this server.
    uploads: bool
    # What may be hard to read.
    warnings: list[str]
    site_name_max: int
    footer_max: int


class EmailDesignIn(BaseModel):
    site_name: str | None = None
    header_colour: str | None = None
    header_text_colour: str | None = None
    accent: str | None = None
    footer: str | None = None


class EmailPreviewOut(BaseModel):
    subject: str
    # The email's HTML, its pictures as data: addresses, for a sandboxed frame.
    html: str
    # Its plain-text part.
    text: str


# Each part as the audit log names it.
PART_NAMES = {
    "site_name": "the site's name",
    "header_colour": "the header colour",
    "header_text_colour": "the header's text colour",
    "accent": "the accent colour",
    "footer": "the footer",
}


def header_url(image: email_design.HeaderImage) -> str:
    return f"/api/site/email-design/header/{image.id}/{image.name}"


def design_out(db: DbSession) -> EmailDesignOut:
    design = email_design.current(db)
    kept = email_design.stored(db)
    image = design.header_image
    return EmailDesignOut(
        site_name=design.site_name,
        header_colour=design.header_colour,
        header_text_colour=design.header_text_colour,
        accent=design.accent,
        footer=design.footer,
        chosen=[part for part in DEFAULTS if kept.get(part)],
        defaults=EmailDesignDefaults(
            site_name=DEFAULTS["site_name"],
            header_colour=DEFAULTS["header_colour"],
            header_text_colour=DEFAULTS["header_text_colour"],
            accent=DEFAULTS["accent"],
        ),
        header_image=(
            HeaderImageOut(
                url=header_url(image), width=image.width, height=image.height, size=image.size
            )
            if image is not None
            else None
        ),
        uploads=pictures.upload_dir() is not None,
        warnings=email_design.warnings(design),
        site_name_max=email_design.SITE_NAME_MAX,
        footer_max=email_design.FOOTER_MAX,
    )


@router.get("")
def get_design(db: DbSession, user: CurrentUser) -> EmailDesignOut:
    require_custodian(user)
    return design_out(db)


@router.put("")
def set_design(body: EmailDesignIn, db: DbSession, user: CurrentUser) -> EmailDesignOut:
    """The site's name, the header's colours, the accent and the footer. Blank parts
    put back Horatio's own."""
    require_custodian(user)
    try:
        parts = email_design.checked(body.model_dump())
    except DesignError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    before = {k: v for k, v in email_design.stored(db).items() if k in DEFAULTS}
    email_design.save(db, parts)
    changed = [part for part in DEFAULTS if before.get(part) != parts.get(part)]
    if changed:
        record(db, user, "mail.design_set", changed=", ".join(PART_NAMES[p] for p in changed))
    db.commit()
    return design_out(db)


@router.post("/header")
def upload_header(
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="JPEG, PNG, WebP or HEIC, up to 10 MB.")],
) -> EmailDesignOut:
    """A picture for the top of every email, replacing any there was. It's kept as a
    PNG or JPEG made small enough to go in every email."""
    require_custodian(user)
    root = pictures.upload_dir()
    if root is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pictures are not set up here.")
    try:
        image = email_design.keep_header(root, file.file.read(pictures.MAX_BYTES + 1))
    except (pictures.PictureError, DesignError) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    kept = email_design.stored(db)
    old = email_design.header_from(kept.get("header_image"))
    with pictures.writing(email_design.header_dir(root, image.id)):
        kept["header_image"] = email_design.header_value(image)
        email_design.put(db, kept)
        record(db, user, "mail.header_uploaded", size=f"{round(image.size / 1024)} KB")
        db.commit()
    if old is not None:
        pictures.remove(email_design.header_dir(root, old.id))
    return design_out(db)


@router.delete("/header")
def remove_header(db: DbSession, user: CurrentUser) -> EmailDesignOut:
    """Emails go back to the site's name, as text, in the header."""
    require_custodian(user)
    kept = email_design.stored(db)
    old = email_design.header_from(kept.pop("header_image", None))
    if old is None:
        return design_out(db)
    email_design.put(db, kept)
    record(db, user, "mail.header_removed")
    db.commit()
    root = pictures.upload_dir()
    if root is not None:
        pictures.remove(email_design.header_dir(root, old.id))
    return design_out(db)


@router.get("/header/{image_id}/{name}", response_class=FileResponse)
def header_file(image_id: uuid.UUID, name: str, db: DbSession, user: CurrentUser) -> FileResponse:
    """The header picture, as emails carry it, for the custodian's card."""
    require_custodian(user)
    image = email_design.current(db).header_image
    root = pictures.upload_dir()
    if image is None or root is None or image.id != image_id or image.name != name:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    path = email_design.header_file(root, image)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such picture.")
    return FileResponse(
        path,
        media_type=email_design.HEADER_FILES[image.name],
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/preview")
def preview(
    db: DbSession, user: CurrentUser, scheme: Literal["light", "dark"] = "light"
) -> EmailPreviewOut:
    """A sample email in the design, as a mail client in light or dark shows it."""
    require_custodian(user)
    shown = email_design.sample(user.display_name)
    page, text = email_design.preview(
        shown.body, email_design.current(db), subject=shown.subject, scheme=scheme
    )
    return EmailPreviewOut(subject=shown.subject, html=page, text=text)


@router.post("/test")
def test_design(db: DbSession, user: CurrentUser) -> MailTestOut:
    """Send the sample email, in the design, to the custodian's own address now."""
    require_custodian(user)
    if (off := mail_off()) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mail is off: {off}")
    shown = email_design.sample(user.display_name)
    mail = email.new_message(
        formataddr((user.display_name, user.email)), shown.subject, mail_sender.sender(db)
    )
    design: Design = email_design.current(db)
    email_design.compose(mail, shown.body, design)
    try:
        email.deliver(mail)
    except SendError as error:
        reason, detail = mail_problem(error)
        record(db, user, "mail.design_test_failed", error=reason)
        db.commit()
        return MailTestOut(ok=False, to=user.email, reason=reason, detail=detail)
    record(db, user, "mail.design_test_sent", to=user.email)
    db.commit()
    return MailTestOut(ok=True, to=user.email)
