"""The game developer blog (issue #1156): who writes, each step of an article's way to
the blog and back, slugs, published articles' changes, tags, the hero picture, and
the audit log and bell that follow."""

import io
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from horatio import blog, pictures
from horatio.config import get_settings
from horatio.models import AuditEvent, EmailNotice
from tests.api_helpers import Person, Troupe, sign_up


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def write(person: Person, troupe_id: str | None = None, **more: Any) -> Any:
    body = {
        "title": "Running your first Elysium",
        "summary": "What I wish I'd known.",
        "body": "Start small.",
        "troupe_id": troupe_id,
        **more,
    }
    return person.client.post("/blog/articles", json=body)


def draft(person: Person, troupe_id: str | None = None, **more: Any) -> dict[str, Any]:
    return ok(write(person, troupe_id, **more), 201)


def submitted(person: Person, troupe_id: str | None = None, **more: Any) -> dict[str, Any]:
    article = draft(person, troupe_id, **more)
    return ok(person.client.post(f"/blog/articles/{article['id']}/submit"))


def published(troupe: Troupe, person: Person | None = None, **more: Any) -> dict[str, Any]:
    article = submitted(person or troupe.storyteller, troupe.id, **more)
    return ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))


def change(person: Person, article: dict[str, Any], **more: Any) -> Any:
    body = {
        "title": article["title"],
        "summary": article["summary"],
        "body": article["body"],
        "troupe_id": article["troupe"]["id"] if article["troupe"] else None,
        **more,
    }
    return person.client.put(f"/blog/articles/{article['id']}", json=body)


def bell(person: Person) -> list[str]:
    return [i["summary"] for i in ok(person.client.get("/notifications"))["items"]]


def queue(troupe: Troupe) -> dict[str, list[str]]:
    found = ok(troupe.custodian.client.get("/blog/queue"))
    return {k: [a["title"] for a in v] for k, v in found.items()}


def archive(troupe: Troupe) -> None:
    ok(troupe.lead.client.post(f"/troupes/{troupe.id}/archive", json={"reason": "Done"}))


# --- who writes ---------------------------------------------------------------------------


def test_every_role_on_staff_writes_naming_their_troupe(troupe: Troupe) -> None:
    staff = {
        "lead": troupe.lead,
        "storyteller": troupe.storyteller,
        "assistant": troupe.assistant,
        "narrator": troupe.narrator,
    }
    for name, person in staff.items():
        writer = ok(person.client.get("/blog/writer"))
        assert writer["can_write"] is True
        assert [t["name"] for t in writer["troupes"]] == ["Lords of the Night"]
        article = draft(person, troupe.id, title=f"Notes from a {name}")
        assert article["status"] == "draft"
        assert article["troupe"]["name"] == "Lords of the Night"
        assert article["author_name"] == name
        assert article["mine"] is True
        ok(person.client.post(f"/blog/articles/{article['id']}/submit"))


def test_a_narrator_writes_and_submits(troupe: Troupe) -> None:
    article = submitted(troupe.narrator, troupe.id)

    assert article["status"] == "submitted"
    assert article["waiting"] == "article"
    assert queue(troupe)["waiting"] == ["Running your first Elysium"]


def test_the_writer_hears_whether_each_troupe_is_public(troupe: Troupe) -> None:
    assert ok(troupe.narrator.client.get("/blog/writer"))["troupes"][0]["public"] is False
    ok(troupe.storyteller.client.put(f"/troupes/{troupe.id}/profile/public", json={"public": True}))

    shown = ok(troupe.narrator.client.get("/blog/writer"))["troupes"][0]
    assert shown == {
        "id": troupe.id,
        "name": "Lords of the Night",
        "archived": False,
        "public": True,
        # Its card on the blog, for the preview (#1160).
        "card": {
            "id": troupe.id,
            "name": "Lords of the Night",
            "abbreviation": "LotN",
            "portrait": None,
            "description": "",
        },
    }
    assert draft(troupe.narrator, troupe.id)["troupe"]["public"] is True


def test_players_and_strangers_dont_write(troupe: Troupe) -> None:
    for person in (troupe.player, troupe.stranger):
        writer = ok(person.client.get("/blog/writer"))
        assert writer == {"can_write": False, "troupes": []}
        refused = write(person)
        assert refused.status_code == 403
        assert refused.json()["detail"] == (
            "Only the staff of a troupe that is running can write for the blog."
        )


def test_the_staff_of_an_archived_troupe_dont_write(troupe: Troupe) -> None:
    article = draft(troupe.narrator, troupe.id)
    archive(troupe)

    assert ok(troupe.narrator.client.get("/blog/writer"))["can_write"] is False
    assert write(troupe.narrator).status_code == 403
    # Nor submit what they wrote before.
    assert troupe.narrator.client.post(f"/blog/articles/{article['id']}/submit").status_code == 403


def test_the_custodian_writes_naming_no_troupe(troupe: Troupe) -> None:
    writer = ok(troupe.custodian.client.get("/blog/writer"))
    assert writer == {"can_write": True, "troupes": []}

    article = submitted(troupe.custodian)

    assert article["troupe"] is None
    # Not a troupe they aren't on staff of, even so.
    assert write(troupe.custodian, troupe.id).status_code == 422


def test_an_article_names_only_a_troupe_its_author_is_on_staff_of(
    troupe: Troupe, client_for: Callable[[], TestClient]
) -> None:
    other = ok(
        troupe.custodian.client.post(
            "/troupes", json={"name": "Court of Ash", "lead_handle": troupe.lead.handle}
        ),
        201,
    )
    # The lead runs both, and chooses.
    assert [t["name"] for t in ok(troupe.lead.client.get("/blog/writer"))["troupes"]] == [
        "Court of Ash",
        "Lords of the Night",
    ]
    assert draft(troupe.lead, other["id"])["troupe"]["name"] == "Court of Ash"
    # The narrator isn't on Court of Ash's staff.
    refused = write(troupe.narrator, other["id"])
    assert refused.status_code == 422
    assert refused.json()["detail"] == "Choose a troupe where you're on staff, or none."
    mine = draft(troupe.narrator, troupe.id)
    assert change(troupe.narrator, mine, troupe_id=other["id"]).status_code == 422
    assert change(troupe.narrator, mine, troupe_id=None).status_code == 200


def test_submitting_checks_the_troupe_again_and_publishing_keeps_it(troupe: Troupe) -> None:
    article = draft(troupe.narrator, troupe.id)
    ok(troupe.lead.client.delete(f"/troupes/{troupe.id}/staff/{troupe.narrator.id}"), 204)

    refused = troupe.narrator.client.post(f"/blog/articles/{article['id']}/submit")

    assert refused.status_code == 403  # on no troupe's staff now
    # On another troupe's staff, they can write, but not name the one they left.
    other = ok(
        troupe.custodian.client.post(
            "/troupes", json={"name": "Court of Ash", "lead_handle": troupe.narrator.handle}
        ),
        201,
    )
    refused = troupe.narrator.client.post(f"/blog/articles/{article['id']}/submit")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "You're no longer on the staff of Lords of the Night, or it is archived: choose"
        " another troupe, or none."
    )
    # Still named while it is a draft, so nothing is lost; they choose another.
    ok(change(troupe.narrator, article, troupe_id=other["id"]))
    ok(troupe.narrator.client.post(f"/blog/articles/{article['id']}/submit"))

    # Once published, it keeps naming the troupe after they leave it.
    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))
    archive_other = troupe.narrator.client.post(
        f"/troupes/{other['id']}/archive", json={"reason": "Done"}
    )
    ok(archive_other)
    again = ok(troupe.narrator.client.get(f"/blog/articles/{article['id']}"))
    assert again["troupe"] == {
        "id": other["id"],
        "name": "Court of Ash",
        "archived": True,
        "public": False,
        "card": None,
    }
    assert done["status"] == again["status"] == "published"


def test_only_its_author_and_the_custodian_see_an_article(troupe: Troupe) -> None:
    article = published(troupe)

    for person in (troupe.lead, troupe.narrator, troupe.player, troupe.stranger):
        assert person.client.get(f"/blog/articles/{article['id']}").status_code == 404
        assert change(person, article, title="Mine now").status_code == 404
    seen = ok(troupe.custodian.client.get(f"/blog/articles/{article['id']}"))
    assert seen["mine"] is False
    # The custodian doesn't change its words: they return it with a note.
    assert change(troupe.custodian, article, title="Better").status_code == 403
    assert [a["title"] for a in ok(troupe.storyteller.client.get("/blog/articles/mine"))] == [
        "Running your first Elysium"
    ]
    assert ok(troupe.lead.client.get("/blog/articles/mine")) == []


def test_only_the_custodian_has_the_queue_and_decides(troupe: Troupe) -> None:
    article = submitted(troupe.storyteller, troupe.id)
    for person in (troupe.lead, troupe.storyteller):
        assert person.client.get("/blog/queue").status_code == 403
        assert person.client.post(f"/blog/articles/{article['id']}/publish").status_code == 403
        assert (
            person.client.post(
                f"/blog/articles/{article['id']}/return", json={"note": "No"}
            ).status_code
            == 403
        )
        assert (
            person.client.put(
                f"/blog/articles/{article['id']}/featured", json={"featured": True}
            ).status_code
            == 403
        )


# --- the way to the blog ------------------------------------------------------------------


def test_an_article_is_submitted_withdrawn_and_published(troupe: Troupe) -> None:
    article = draft(troupe.storyteller, troupe.id)
    assert queue(troupe)["waiting"] == []

    sent = ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert sent["status"] == "submitted"
    assert sent["submitted_at"] is not None
    # It can't be changed while it waits, nor sent twice.
    assert change(troupe.storyteller, sent, title="Later").status_code == 409
    again = troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit")
    assert again.status_code == 409

    back = ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/withdraw"))
    assert back["status"] == "draft"
    assert queue(troupe)["waiting"] == []
    ok(change(troupe.storyteller, back, body="Start small. Then grow."))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert queue(troupe)["waiting"] == ["Running your first Elysium"]

    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    assert done["status"] == "published"
    assert done["published_at"] is not None
    assert done["waiting"] is None
    assert done["body"] == "Start small. Then grow."
    assert queue(troupe) == {
        "waiting": [],
        "published": ["Running your first Elysium"],
        "unpublished": [],
    }
    # Published once: nothing waits to publish again.
    path = f"/blog/articles/{article['id']}"
    assert troupe.custodian.client.post(f"{path}/publish").status_code == 409
    assert troupe.storyteller.client.post(f"{path}/withdraw").status_code == 409


def test_an_empty_article_isnt_submitted(troupe: Troupe) -> None:
    article = draft(troupe.storyteller, troupe.id, body="  ")

    refused = troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit")

    assert refused.status_code == 422
    assert refused.json()["detail"] == "Write the article before you submit it."


def test_the_custodian_returns_an_article_with_a_note(troupe: Troupe) -> None:
    article = submitted(troupe.storyteller, troupe.id)
    # Only one waiting, and only with a note.
    path = f"/blog/articles/{article['id']}/return"
    assert troupe.custodian.client.post(path, json={"note": ""}).status_code == 422

    back = ok(troupe.custodian.client.post(path, json={"note": "Say who it's for."}))

    assert back["status"] == "draft"
    assert back["note"] == "Say who it's for."
    assert queue(troupe)["waiting"] == []
    assert troupe.custodian.client.post(path, json={"note": "Again"}).status_code == 409
    # Its author changes it and sends it again; publishing clears the note.
    ok(change(troupe.storyteller, back, summary="For new storytellers."))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))
    assert done["note"] == ""


def test_the_custodian_unpublishes_with_a_reason_and_it_comes_back(troupe: Troupe) -> None:
    article = published(troupe)
    first = article["published_at"]
    ok(
        troupe.custodian.client.put(
            f"/blog/articles/{article['id']}/featured", json={"featured": True}
        )
    )
    path = f"/blog/articles/{article['id']}/unpublish"
    assert troupe.custodian.client.post(path, json={"reason": ""}).status_code == 422

    down = ok(troupe.custodian.client.post(path, json={"reason": "It names a real player."}))

    assert down["status"] == "unpublished"
    assert down["note"] == "It names a real player."
    assert down["unpublished_at"] is not None
    assert down["featured"] is False
    assert queue(troupe)["unpublished"] == ["Running your first Elysium"]
    assert troupe.custodian.client.post(path, json={"reason": "Again"}).status_code == 409
    # Its author changes it in place, nothing of it being public, and sends it again.
    changed = ok(change(troupe.storyteller, down, body="Start small, anonymously."))
    assert changed["revision"] is None
    assert changed["body"] == "Start small, anonymously."
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    back = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))
    assert back["status"] == "published"
    # Its date on the blog is still when it was first published.
    assert back["published_at"] == first
    assert back["revised_at"] is not None
    assert back["unpublished_at"] is None


def test_only_a_published_article_is_featured(troupe: Troupe) -> None:
    article = submitted(troupe.storyteller, troupe.id)
    path = f"/blog/articles/{article['id']}/featured"
    refused = troupe.custodian.client.put(path, json={"featured": True})
    assert refused.status_code == 409
    troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish")

    assert ok(troupe.custodian.client.put(path, json={"featured": True}))["featured"] is True
    assert ok(troupe.custodian.client.put(path, json={"featured": False}))["featured"] is False


def test_a_draft_never_published_can_be_deleted_by_its_author(troupe: Troupe) -> None:
    article = draft(troupe.storyteller, troupe.id)
    assert troupe.custodian.client.delete(f"/blog/articles/{article['id']}").status_code == 403
    ok(troupe.storyteller.client.delete(f"/blog/articles/{article['id']}"), 204)
    assert troupe.storyteller.client.get(f"/blog/articles/{article['id']}").status_code == 404

    kept = published(troupe)
    refused = troupe.storyteller.client.delete(f"/blog/articles/{kept['id']}")
    assert refused.status_code == 409


# --- changing a published article ---------------------------------------------------------


def test_a_published_articles_changes_wait_while_it_stays_up(troupe: Troupe) -> None:
    article = published(troupe)

    changed = ok(change(troupe.storyteller, article, title="Your first Elysium", body="New."))

    # What is published is as it was; the changes are its revision.
    assert changed["title"] == "Running your first Elysium"
    assert changed["body"] == "Start small."
    assert changed["revision"]["title"] == "Your first Elysium"
    assert changed["revision"]["submitted_at"] is None
    assert changed["waiting"] is None
    # Nothing to send until it changes.
    plain = published(troupe, troupe.assistant, title="Another")
    unchanged = troupe.assistant.client.post(f"/blog/articles/{plain['id']}/submit")
    assert unchanged.status_code == 409

    sent = ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert sent["status"] == "published"
    assert sent["waiting"] == "changes"
    assert queue(troupe)["waiting"] == ["Running your first Elysium"]
    assert change(troupe.storyteller, sent, body="More.").status_code == 409
    # Withdrawn and sent again.
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/withdraw"))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))

    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    assert done["title"] == "Your first Elysium"
    assert done["body"] == "New."
    assert done["revision"] is None
    assert done["revised_at"] is not None
    assert done["published_at"] == article["published_at"]
    # Its address stays as it was published.
    assert done["slug"] == "running-your-first-elysium"


def test_a_published_articles_changes_are_returned_or_thrown_away(troupe: Troupe) -> None:
    article = published(troupe)
    ok(change(troupe.storyteller, article, body="Rewritten."))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))

    back = ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/return", json={"note": "Keep the old ending."}
        )
    )

    assert back["status"] == "published"
    assert back["body"] == "Start small."
    assert back["revision"]["body"] == "Rewritten."
    assert back["revision"]["submitted_at"] is None
    assert back["note"] == "Keep the old ending."
    assert queue(troupe)["waiting"] == []

    gone = ok(troupe.storyteller.client.delete(f"/blog/articles/{article['id']}/revision"))
    assert gone["revision"] is None
    assert gone["body"] == "Start small."
    again = troupe.storyteller.client.delete(f"/blog/articles/{article['id']}/revision")
    assert again.status_code == 409


def test_unpublishing_makes_a_revision_the_article(troupe: Troupe) -> None:
    article = published(troupe)
    ok(change(troupe.storyteller, article, body="Rewritten."))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))

    down = ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/unpublish", json={"reason": "Out of date."}
        )
    )

    assert down["revision"] is None
    assert down["body"] == "Rewritten."
    assert down["waiting"] is None


# --- slugs --------------------------------------------------------------------------------


def test_slugs_come_from_the_title_and_are_unique(troupe: Troupe) -> None:
    first = draft(troupe.storyteller, troupe.id, title="Élysium: the Basics!")
    second = draft(troupe.assistant, troupe.id, title="Elysium -- the basics")

    assert first["slug"] == "elysium-the-basics"
    assert second["slug"] == "elysium-the-basics-2"
    assert draft(troupe.lead, troupe.id, title="???")["slug"] == "article"
    assert blog.slugify("x" * 100 + " tail") == "x" * 80


def test_a_slug_follows_the_title_until_chosen_and_is_fixed_once_published(
    troupe: Troupe,
) -> None:
    article = draft(troupe.storyteller, troupe.id, title="Untitled")
    article = ok(change(troupe.storyteller, article, title="Boons for beginners"))
    assert article["slug"] == "boons-for-beginners"
    other = draft(troupe.assistant, troupe.id, title="Something else")
    path = f"/blog/articles/{article['id']}/slug"

    clash = troupe.storyteller.client.put(path, json={"slug": other["slug"]})
    assert clash.status_code == 409
    assert clash.json()["detail"] == "Another article has that address."
    chosen = ok(troupe.storyteller.client.put(path, json={"slug": "Boons 101"}))
    assert chosen["slug"] == "boons-101"
    # Set by hand, the title no longer changes it.
    retitled = ok(change(troupe.storyteller, chosen, title="Boons, for beginners"))
    assert retitled["slug"] == "boons-101"
    # The custodian may change it too, as it waits.
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    assert ok(troupe.custodian.client.put(path, json={"slug": "boons"}))["slug"] == "boons"
    assert troupe.lead.client.put(path, json={"slug": "mine"}).status_code == 404

    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    assert done["slug_fixed"] is True
    refused = troupe.custodian.client.put(path, json={"slug": "boons-again"})
    assert refused.status_code == 409


# --- tags ---------------------------------------------------------------------------------


def test_the_tags_are_seeded_in_order(troupe: Troupe) -> None:
    tags = ok(troupe.player.client.get("/blog/tags"))

    assert [t["name"] for t in tags] == [
        "How to play",
        "Storytelling",
        "Running a game",
        "New players",
        "Tips and tricks",
        "Downtimes",
        "Politics and boons",
        "Combat and challenges",
        "Setting and lore",
        "Safety and consent",
        "Using Horatio",
        "Community",
    ]
    assert tags[0]["slug"] == "how-to-play"


def test_the_custodian_tags_an_article_and_its_author_only_while_writing(
    troupe: Troupe,
) -> None:
    tags = {t["name"]: t["id"] for t in ok(troupe.player.client.get("/blog/tags"))}
    article = draft(troupe.storyteller, troupe.id)
    path = f"/blog/articles/{article['id']}/tags"
    mine = ok(troupe.storyteller.client.put(path, json={"tag_ids": [tags["Storytelling"]]}))
    assert [t["name"] for t in mine["tags"]] == ["Storytelling"]
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    refused = troupe.storyteller.client.put(path, json={"tag_ids": []})
    assert refused.status_code == 409

    done = ok(
        troupe.custodian.client.put(
            path, json={"tag_ids": [tags["Community"], tags["How to play"], tags["Community"]]}
        )
    )

    assert [t["name"] for t in done["tags"]] == ["How to play", "Community"]
    unknown = troupe.custodian.client.put(path, json={"tag_ids": [str(uuid.uuid4())]})
    assert unknown.status_code == 422
    assert troupe.lead.client.put(path, json={"tag_ids": []}).status_code == 404


# --- the hero picture ---------------------------------------------------------------------


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(get_settings(), "upload_dir", str(directory))
    return directory


def png(colour: tuple[int, int, int] = (120, 20, 20)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (1600, 900), colour).save(out, "PNG")
    return out.getvalue()


def upload(person: Person, article_id: str, colour: tuple[int, int, int] = (120, 20, 20)) -> Any:
    return person.client.post(
        f"/blog/articles/{article_id}/picture", files={"file": ("p.png", png(colour), "image/png")}
    )


def fetch(person: Person, picture: str, name: str = "1200.webp") -> Any:
    return person.client.get(f"{picture}/{name}".removeprefix("/api"))


def test_a_hero_picture_is_kept_apart_from_any_troupe_for_its_author_and_the_custodian(
    troupe: Troupe, kept: Path
) -> None:
    article = draft(troupe.storyteller, troupe.id)

    added = ok(upload(troupe.storyteller, article["id"]))

    picture = added["picture"]
    assert picture.startswith(f"/api/blog/articles/{article['id']}/pictures/")
    assert (kept / "blog" / picture.rsplit("/", 1)[1] / "1200.webp").is_file()
    shown = fetch(troupe.storyteller, picture)
    assert shown.status_code == 200
    # With no crop, the widest 2:1 frame in the middle.
    with Image.open(io.BytesIO(shown.content)) as image:
        assert image.size == (1200, 600)
    assert fetch(troupe.custodian, picture, "600.webp").status_code == 200
    assert fetch(troupe.lead, picture).status_code == 404
    assert fetch(troupe.storyteller, picture, "full.webp").status_code == 404
    assert upload(troupe.custodian, article["id"]).status_code == 403

    removed = ok(troupe.storyteller.client.delete(f"/blog/articles/{article['id']}/picture"))
    assert removed["picture"] is None
    assert not (kept / "blog" / picture.rsplit("/", 1)[1]).exists()


def test_a_hero_picture_is_cut_to_the_frame_its_author_places(troupe: Troupe, kept: Path) -> None:
    article = draft(troupe.storyteller, troupe.id)
    # Left half of a 1600 x 900 picture that is red on the left and blue on the right.
    two = Image.new("RGB", (1600, 900), (200, 0, 0))
    two.paste((0, 0, 200), (800, 0, 1600, 900))
    out = io.BytesIO()
    two.save(out, "PNG")

    added = ok(
        troupe.storyteller.client.post(
            f"/blog/articles/{article['id']}/picture",
            files={"file": ("p.png", out.getvalue(), "image/png")},
            data={"crop_x": "0", "crop_y": "0.5", "crop_size": "0.5"},
        )
    )

    shown = fetch(troupe.storyteller, added["picture"], "600.webp")
    with Image.open(io.BytesIO(shown.content)) as image:
        # 800 x 400 from the left edge, halfway down, made 600 x 300: all red.
        assert image.size == (600, 300)
        red, _, blue = image.convert("RGB").getpixel((590, 150))  # type: ignore[misc]
        assert red > 150 and blue < 50


def test_the_hero_frame_stays_inside_the_picture() -> None:
    crop = pictures.Crop(0.9, 0.9, 2.0)
    assert pictures.hero_box(1600, 900, None) == (0, 50, 1600, 850)
    assert pictures.hero_box(1600, 900, crop) == (0, 100, 1600, 900)
    assert pictures.hero_box(600, 1000, None) == (0, 350, 600, 650)
    assert pictures.hero_box(1, 1, None) == (0, 0, 1, 1)


def test_a_published_articles_new_picture_waits_with_its_changes(
    troupe: Troupe, kept: Path
) -> None:
    article = draft(troupe.storyteller, troupe.id)
    old = ok(upload(troupe.storyteller, article["id"]))["picture"]
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))

    changed = ok(upload(troupe.storyteller, article["id"], (20, 20, 120)))

    new = changed["revision"]["picture"]
    assert changed["picture"] == old
    assert new != old
    assert fetch(troupe.storyteller, old).status_code == 200
    assert fetch(troupe.storyteller, new).status_code == 200
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    done = ok(troupe.custodian.client.post(f"/blog/articles/{article['id']}/publish"))
    assert done["picture"] == new
    # The old one's files go once it is replaced.
    assert not (kept / "blog" / old.rsplit("/", 1)[1]).exists()
    assert fetch(troupe.storyteller, old).status_code == 404


# --- the audit log and the bell -----------------------------------------------------------


def test_every_step_is_in_the_audit_log(troupe: Troupe, session: Session) -> None:
    article = published(troupe)
    ok(change(troupe.storyteller, article, body="Rewritten."))
    ok(troupe.storyteller.client.post(f"/blog/articles/{article['id']}/submit"))
    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/return", json={"note": "Shorter."}
        )
    )
    ok(
        troupe.custodian.client.put(
            f"/blog/articles/{article['id']}/featured", json={"featured": True}
        )
    )
    ok(
        troupe.custodian.client.post(
            f"/blog/articles/{article['id']}/unpublish", json={"reason": "Out of date."}
        )
    )

    found = ok(troupe.custodian.client.get("/audit", params={"group": "blog"}))["entries"]

    assert [e["message"] for e in reversed(found)] == [
        "storyteller started writing the blog article “Running your first Elysium”.",
        "storyteller sent the blog article “Running your first Elysium” to the custodian to"
        " publish.",
        "custodian published the blog article “Running your first Elysium”.",
        "storyteller sent changes to the blog article “Running your first Elysium” to the"
        " custodian to publish.",
        "custodian returned changes to the blog article “Running your first Elysium” to its"
        " author: Shorter.",
        "custodian featured the blog article “Running your first Elysium”.",
        "custodian unpublished the blog article “Running your first Elysium”: Out of date.",
    ]
    levels = {e["action"]: e["level"] for e in found}
    assert levels["blog.published"] == "notice"
    assert levels["blog.unpublished"] == "notice"
    assert levels["blog.returned"] == "notice"
    assert levels["blog.submitted"] == "info"
    # Outside any troupe's log: the blog is the whole site's.
    events = session.scalars(select(AuditEvent).where(AuditEvent.action.startswith("blog."))).all()
    assert {e.troupe_id for e in events} == {None}
    log = ok(troupe.lead.client.get(f"/troupes/{troupe.id}/log"))
    assert not [e for e in log if e["action"].startswith("blog.")]


def test_its_author_hears_of_publishing_returning_and_unpublishing(troupe: Troupe) -> None:
    article = submitted(troupe.narrator, troupe.id)
    path = f"/blog/articles/{article['id']}"
    ok(troupe.custodian.client.post(f"{path}/return", json={"note": "Add an example."}))
    ok(troupe.narrator.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    ok(change(troupe.narrator, article, body="Better."))
    ok(troupe.narrator.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    ok(troupe.custodian.client.post(f"{path}/unpublish", json={"reason": "Too long."}))

    assert bell(troupe.narrator) == [
        "The custodian unpublished your article “Running your first Elysium”: Too long.",
        "Your changes to “Running your first Elysium” are published on the blog.",
        "Your article “Running your first Elysium” is published on the blog.",
        "The custodian returned your article “Running your first Elysium”: Add an example.",
    ]
    links = {i["link"] for i in ok(troupe.narrator.client.get("/notifications"))["items"]}
    assert links == {f"/blog/write/{article['id']}"}
    # Nobody else hears of it.
    assert not [s for s in bell(troupe.lead) if "Elysium" in s]


def tasks(person: Person) -> list[dict[str, Any]]:
    """The custodian's blog tasks in the bell (#1170)."""
    items = ok(person.client.get("/notifications"))["items"]
    return [i for i in items if i["kind"] == "blog_article"]


def test_the_custodian_has_a_task_while_an_article_waits(troupe: Troupe) -> None:
    article = submitted(troupe.narrator, troupe.id)
    path = f"/blog/articles/{article['id']}"

    [task] = tasks(troupe.custodian)
    assert task["summary"] == (
        "narrator asks you to publish the blog article “Running your first Elysium”"
    )
    assert task["task"] is True
    assert task["link"] == f"/custodian/blog#article-{article['id']}"
    # Nobody else has it: not its author, nor the troupe's lead.
    assert tasks(troupe.narrator) == tasks(troupe.lead) == []

    # It goes when the author withdraws it, comes back when they send it again, and
    # goes when the custodian returns it or publishes it.
    ok(troupe.narrator.client.post(f"{path}/withdraw"))
    assert tasks(troupe.custodian) == []
    ok(troupe.narrator.client.post(f"{path}/submit"))
    assert len(tasks(troupe.custodian)) == 1
    ok(troupe.custodian.client.post(f"{path}/return", json={"note": "Add an example."}))
    assert tasks(troupe.custodian) == []
    ok(troupe.narrator.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/publish"))
    assert tasks(troupe.custodian) == []


def test_the_custodian_has_a_task_while_a_published_articles_changes_wait(
    troupe: Troupe,
) -> None:
    article = published(troupe, troupe.narrator)
    path = f"/blog/articles/{article['id']}"
    ok(change(troupe.narrator, article, title="Your first Elysium"))
    # Changes still being written wait for nobody.
    assert tasks(troupe.custodian) == []

    ok(troupe.narrator.client.post(f"{path}/submit"))
    [task] = tasks(troupe.custodian)
    assert task["summary"] == (
        "narrator asks you to publish changes to the blog article “Your first Elysium”"
    )
    assert task["link"] == f"/custodian/blog#article-{article['id']}"

    # It goes when the author withdraws them, or the custodian returns or publishes them.
    ok(troupe.narrator.client.post(f"{path}/withdraw"))
    assert tasks(troupe.custodian) == []
    ok(troupe.narrator.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/return", json={"note": "Not yet."}))
    assert tasks(troupe.custodian) == []
    ok(troupe.narrator.client.post(f"{path}/submit"))
    assert len(tasks(troupe.custodian)) == 1
    ok(troupe.custodian.client.post(f"{path}/publish"))
    assert tasks(troupe.custodian) == []

    # Unpublishing takes the changes in, and the task with them.
    ok(change(troupe.narrator, article, body="Once more."))
    ok(troupe.narrator.client.post(f"{path}/submit"))
    ok(troupe.custodian.client.post(f"{path}/unpublish", json={"reason": "Out of date."}))
    assert tasks(troupe.custodian) == []


def test_the_custodian_is_emailed_of_an_article_waiting_if_they_choose(
    troupe: Troupe, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "mail_from", "Horatio <horatio@example.org>")
    article = submitted(troupe.narrator, troupe.id)
    ok(troupe.narrator.client.post(f"/blog/articles/{article['id']}/withdraw"))
    # Off until they choose it.
    assert session.scalars(select(EmailNotice)).all() == []

    ok(troupe.custodian.client.patch("/preferences", json={"email_blog_queue": True}))
    ok(troupe.narrator.client.post(f"/blog/articles/{article['id']}/submit"))

    [notice] = session.scalars(select(EmailNotice)).all()
    assert str(notice.user_id) == troupe.custodian.id
    assert notice.topic == "blog_queue"
    assert notice.summary == (
        "narrator asks you to publish the blog article “Running your first Elysium”"
    )
    assert notice.link == f"/custodian/blog#article-{article['id']}"


def test_a_custodian_and_staff_member_sees_their_troupes(
    client_for: Callable[[], TestClient], session: Session
) -> None:
    custodian = sign_up(client_for, "keeper", custodian=True, session=session)
    made = ok(
        custodian.client.post(
            "/troupes", json={"name": "Keepers", "lead_handle": custodian.handle}
        ),
        201,
    )
    writer = ok(custodian.client.get("/blog/writer"))
    assert [t["id"] for t in writer["troupes"]] == [made["id"]]
    assert draft(custodian, made["id"])["troupe"]["name"] == "Keepers"
