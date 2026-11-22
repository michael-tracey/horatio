"""The sizes of a blog article's pictures (#1183): its hero picture's and those in its
words, each copy's width and height in pixels, so its pages keep the pictures' room
before they load and the words don't jump.

They are kept when a picture is uploaded. One uploaded before then (migration 0282)
gets them the first time it is shown, read from its files and kept: the migration
can't read them, as it runs where the uploads aren't. A picture whose files are
missing has no sizes, and is drawn without them, as before.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from horatio import pictures
from horatio.models import BlogHeroPicture, BlogPostPicture

Sizes = pictures.Sizes


def keep_hero(db: Session, article_id: uuid.UUID, picture_id: uuid.UUID, sizes: Sizes) -> None:
    """A new hero picture's sizes, saved with the change that makes it the article's."""
    db.add(BlogHeroPicture(id=picture_id, post_id=article_id, sizes=sizes))


def forget_hero(db: Session, picture_id: uuid.UUID) -> None:
    """A hero picture's sizes, once its files have gone."""
    db.execute(delete(BlogHeroPicture).where(BlogHeroPicture.id == picture_id))


def hero_sizes(
    db: Session, heroes: Iterable[tuple[uuid.UUID, uuid.UUID | None]]
) -> dict[uuid.UUID, Sizes]:
    """The sizes of hero pictures, by picture id, given (article id, picture id) pairs:
    the article's picture, or its revision's. Those not known yet are read from their
    files and kept, so the next reader doesn't read them again."""
    wanted = {picture: article for article, picture in heroes if picture is not None}
    if not wanted:
        return {}
    known = {
        h.id: h.sizes
        for h in db.scalars(select(BlogHeroPicture).where(BlogHeroPicture.id.in_(wanted)))
    }
    root = pictures.upload_dir()
    filled = False
    for picture, article in wanted.items():
        if picture in known or root is None:
            continue
        sizes = pictures.post_picture_sizes(pictures.blog_picture_dir(root, picture))
        if sizes is None:
            continue
        # Two readers at once may both find it unknown: the second keeps the same.
        db.execute(
            insert(BlogHeroPicture)
            .values(id=picture, post_id=article, sizes=sizes)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        known[picture] = sizes
        filled = True
    if filled:
        db.commit()
    return known


def body_sizes(db: Session, named: Iterable[tuple[uuid.UUID, uuid.UUID]]) -> dict[uuid.UUID, Sizes]:
    """The sizes of pictures in articles' words, by picture id, given (article id,
    picture id) pairs: only an article's own pictures. Those not known yet are read
    from their files and kept."""
    wanted = {picture: article for article, picture in named}
    if not wanted:
        return {}
    root = pictures.upload_dir()
    known: dict[uuid.UUID, Sizes] = {}
    filled = False
    for picture in db.scalars(select(BlogPostPicture).where(BlogPostPicture.id.in_(wanted))):
        if wanted[picture.id] != picture.post_id:
            continue
        if picture.sizes is None and root is not None:
            directory = pictures.body_picture_dir(root, picture.post_id, picture.id)
            picture.sizes = pictures.post_picture_sizes(directory)
            filled = filled or picture.sizes is not None
        if picture.sizes is not None:
            known[picture.id] = picture.sizes
    if filled:
        db.commit()
    return known
