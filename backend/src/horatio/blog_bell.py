"""Everyone hears of a new blog article on the bell (#1165): once, when the custodian
first publishes it, not when they publish its changes, nor when it comes back after
being unpublished.

The notice goes to every account but its author's (they hear "your article is
published" instead, horatio.blog), a merged one's or a suspended one's, unless the
person turned "New blog articles" off on Account › Notifications. It comes only to
the bell: no email, push or Discord. It links to the article on the blog.

Publishing doesn't write the notices: an article published and not yet told
(`everyone_told_at` is None) is told by the delivery worker (horatio.delivery), in
one statement for everyone, so the custodian's request doesn't wait on the whole
site's notices. An article unpublished before it was told is told once it is
published again. A server can turn the notices off (`blog_bell`), as the e2e suite
does.
"""

from sqlalchemy import func, insert, literal, select
from sqlalchemy.orm import Session

from horatio import notification_choices, suspensions
from horatio.blog import now
from horatio.config import get_settings
from horatio.models import BlogPost, Notification, User

KIND = "blog.new"


def link(article: BlogPost) -> str:
    """The article on the blog."""
    return f"/blog/{article.slug}"


def summary(db: Session, article: BlogPost) -> str:
    author = db.get_one(User, article.author_id)
    return f"New on the blog: “{article.title}”, by {author.display_name}."


def tell_everyone(db: Session, article: BlogPost) -> None:
    """Leave the notice of `article` in the bell of everyone who has it come there.
    With the server's `blog_bell` off, it counts as told without a notice."""
    article.everyone_told_at = now()
    if not get_settings().blog_bell:
        return
    topic = notification_choices.topic_for(KIND)
    setting = topic.setting("bell")
    default = "true" if topic.routes["bell"].default else "false"
    db.execute(
        insert(Notification).from_select(
            ["user_id", "kind", "summary", "link"],
            select(
                User.id, literal(KIND), literal(summary(db, article)), literal(link(article))
            ).where(
                User.id != article.author_id,
                User.merged_into_id.is_(None),
                ~suspensions.suspended_user(),
                # As notification_choices.chosen: what they chose, or the default.
                func.coalesce(User.preferences.op("->>")(setting), default) == "true",
            ),
        )
    )


def tell_due(db: Session) -> int:
    """Tell everyone of each article published and not yet told, the first published
    first. Each is locked while it is told, so two workers never tell it twice.
    Returns how many articles were told of."""
    due = db.scalars(
        select(BlogPost)
        .where(BlogPost.status == "published", BlogPost.everyone_told_at.is_(None))
        .order_by(BlogPost.published_at, BlogPost.id)
        .with_for_update(skip_locked=True)
    ).all()
    for article in due:
        tell_everyone(db, article)
    return len(due)


def tell_due_now() -> int:
    """`tell_due` in a session of its own, for the delivery worker."""
    from horatio.db import get_sessionmaker

    with get_sessionmaker()() as db:
        told = tell_due(db)
        db.commit()
        return told
