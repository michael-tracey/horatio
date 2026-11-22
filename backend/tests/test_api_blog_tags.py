"""The blog's tags as the custodian keeps them (issue #1161): adding, renaming (and what
it does to a tag's slug), merging, retiring and bringing back, reordering, the counts,
who may, and the audit log."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.api_helpers import Troupe


@pytest.fixture
def troupe(client_for: Callable[[], TestClient], session: Session) -> Troupe:
    return Troupe(client_for, session)


def ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if response.content else None


def kept(troupe: Troupe) -> dict[str, dict[str, Any]]:
    return {t["name"]: t for t in ok(troupe.custodian.client.get("/blog/tags/kept"))}


def choosable(troupe: Troupe) -> list[str]:
    return [t["name"] for t in ok(troupe.player.client.get("/blog/tags"))]


def article(troupe: Troupe, tags: list[str], *, publish: bool = False, title: str = "") -> str:
    """An article by the storyteller with `tags`, published if asked."""
    ids = {t["name"]: t["id"] for t in ok(troupe.custodian.client.get("/blog/tags/kept"))}
    made = ok(
        troupe.storyteller.client.post(
            "/blog/articles",
            json={"title": title or "Running your first Elysium", "body": "Start small."},
        ),
        201,
    )
    path = f"/blog/articles/{made['id']}"
    ok(troupe.storyteller.client.put(f"{path}/tags", json={"tag_ids": [ids[t] for t in tags]}))
    if publish:
        ok(troupe.storyteller.client.post(f"{path}/submit"))
        ok(troupe.custodian.client.post(f"{path}/publish"))
    return made["id"]


def tags_on(troupe: Troupe, article_id: str) -> list[str]:
    found = ok(troupe.custodian.client.get(f"/blog/articles/{article_id}"))
    return [t["name"] for t in found["tags"]]


def test_only_the_custodian_keeps_the_tags(troupe: Troupe) -> None:
    tag = kept(troupe)["Community"]["id"]
    for person in (troupe.lead, troupe.storyteller, troupe.player):
        assert person.client.get("/blog/tags/kept").status_code == 403
        assert person.client.post("/blog/tags", json={"name": "Mine"}).status_code == 403
        assert person.client.put(f"/blog/tags/{tag}", json={"name": "Ours"}).status_code == 403
        retiring = person.client.put(f"/blog/tags/{tag}/retired", json={"retired": True})
        assert retiring.status_code == 403
        merging = person.client.post(f"/blog/tags/{tag}/merge", json={"into_id": tag})
        assert merging.status_code == 403
        assert person.client.put("/blog/tag-order", json={"tag_ids": []}).status_code == 403


def test_the_custodian_adds_a_tag_at_the_end_with_a_slug(troupe: Troupe) -> None:
    found = ok(troupe.custodian.client.post("/blog/tags", json={"name": "  Boons & Prestation "}))

    assert found[-1]["name"] == "Boons & Prestation"
    assert found[-1]["slug"] == "boons-prestation"
    assert found[-1] | {"id": None} == {
        "id": None,
        "name": "Boons & Prestation",
        "slug": "boons-prestation",
        "slug_fixed": False,
        "retired": False,
        "articles": 0,
        "published": 0,
    }
    assert choosable(troupe)[-1] == "Boons & Prestation"
    # Another name with the same slug gets one of its own.
    again = ok(troupe.custodian.client.post("/blog/tags", json={"name": "Boons, prestation"}))
    assert again[-1]["slug"] == "boons-prestation-2"


def test_names_are_unique_whatever_the_case(troupe: Troupe) -> None:
    refused = troupe.custodian.client.post("/blog/tags", json={"name": "storytelling"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "There is already a tag called Storytelling."
    community = kept(troupe)["Community"]["id"]
    clash = troupe.custodian.client.put(f"/blog/tags/{community}", json={"name": "DOWNTIMES"})
    assert clash.status_code == 409
    assert troupe.custodian.client.post("/blog/tags", json={"name": "   "}).status_code == 422

    # A tag may change only its case.
    found = ok(troupe.custodian.client.put(f"/blog/tags/{community}", json={"name": "COMMUNITY"}))
    assert "COMMUNITY" in [t["name"] for t in found]


def test_a_rename_moves_the_slug_until_a_published_article_carries_the_tag(
    troupe: Troupe,
) -> None:
    tags = kept(troupe)
    # A draft carrying it doesn't fix it: nothing public links there yet.
    article(troupe, ["Community"])
    renamed = ok(
        troupe.custodian.client.put(
            f"/blog/tags/{tags['Community']['id']}", json={"name": "Our communities"}
        )
    )
    assert {t["name"]: t["slug"] for t in renamed}["Our communities"] == "our-communities"

    article(troupe, ["Downtimes"], publish=True, title="Downtimes done well")
    assert kept(troupe)["Downtimes"]["slug_fixed"] is True
    fixed = ok(
        troupe.custodian.client.put(
            f"/blog/tags/{tags['Downtimes']['id']}", json={"name": "Downtime actions"}
        )
    )
    assert {t["name"]: t["slug"] for t in fixed}["Downtime actions"] == "downtimes"


def test_each_tag_counts_its_articles_and_those_published(troupe: Troupe) -> None:
    article(troupe, ["Storytelling", "Community"])
    article(troupe, ["Storytelling"], publish=True, title="Scenes that breathe")

    tags = kept(troupe)

    assert (tags["Storytelling"]["articles"], tags["Storytelling"]["published"]) == (2, 1)
    assert (tags["Community"]["articles"], tags["Community"]["published"]) == (1, 0)
    assert (tags["Downtimes"]["articles"], tags["Downtimes"]["published"]) == (0, 0)


def test_a_retired_tag_stays_on_its_articles_but_isnt_chosen(troupe: Troupe) -> None:
    tags = kept(troupe)
    had = article(troupe, ["Community", "Storytelling"])
    other = article(troupe, [], title="Something else")

    found = ok(
        troupe.custodian.client.put(
            f"/blog/tags/{tags['Community']['id']}/retired", json={"retired": True}
        )
    )

    assert {t["name"]: t["retired"] for t in found}["Community"] is True
    assert "Community" not in choosable(troupe)
    assert tags_on(troupe, had) == ["Storytelling", "Community"]
    # It stays when the article's other tags change, and can be taken off...
    keep = troupe.custodian.client.put(
        f"/blog/articles/{had}/tags",
        json={"tag_ids": [tags["Community"]["id"], tags["Downtimes"]["id"]]},
    )
    assert [t["name"] for t in ok(keep)["tags"]] == ["Downtimes", "Community"]
    # ...but isn't put on another.
    refused = troupe.custodian.client.put(
        f"/blog/articles/{other}/tags", json={"tag_ids": [tags["Community"]["id"]]}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Community is retired")

    back = ok(
        troupe.custodian.client.put(
            f"/blog/tags/{tags['Community']['id']}/retired", json={"retired": False}
        )
    )
    assert {t["name"]: t["retired"] for t in back}["Community"] is False
    assert "Community" in choosable(troupe)


def test_merging_moves_every_article_to_the_other_tag_and_removes_it(troupe: Troupe) -> None:
    tags = kept(troupe)
    both = article(troupe, ["Tips and tricks", "How to play"])
    one = article(troupe, ["Tips and tricks"], publish=True, title="Ten tips")

    found = ok(
        troupe.custodian.client.post(
            f"/blog/tags/{tags['Tips and tricks']['id']}/merge",
            json={"into_id": tags["How to play"]["id"]},
        )
    )

    names = {t["name"]: t for t in found}
    assert "Tips and tricks" not in names
    assert (names["How to play"]["articles"], names["How to play"]["published"]) == (2, 1)
    assert tags_on(troupe, both) == ["How to play"]
    assert tags_on(troupe, one) == ["How to play"]
    gone = troupe.custodian.client.put(
        f"/blog/tags/{tags['Tips and tricks']['id']}", json={"name": "Tips"}
    )
    assert gone.status_code == 404


def test_a_tag_isnt_merged_into_itself_or_a_retired_one(troupe: Troupe) -> None:
    tags = kept(troupe)
    community = tags["Community"]["id"]
    itself = troupe.custodian.client.post(
        f"/blog/tags/{community}/merge", json={"into_id": community}
    )
    assert itself.status_code == 422
    ok(
        troupe.custodian.client.put(
            f"/blog/tags/{tags['Downtimes']['id']}/retired", json={"retired": True}
        )
    )
    retired = troupe.custodian.client.post(
        f"/blog/tags/{community}/merge", json={"into_id": tags["Downtimes"]["id"]}
    )
    assert retired.status_code == 409
    assert "Community" in kept(troupe)


def test_the_custodian_reorders_every_tag(troupe: Troupe) -> None:
    ids = [t["id"] for t in ok(troupe.custodian.client.get("/blog/tags/kept"))]
    ok(troupe.custodian.client.put(f"/blog/tags/{ids[0]}/retired", json={"retired": True}))
    order = list(reversed(ids))

    found = ok(troupe.custodian.client.put("/blog/tag-order", json={"tag_ids": order}))

    assert [t["id"] for t in found] == order
    assert choosable(troupe)[0] == "Community"
    # Retired tags keep their place among the rest, out of the choices.
    assert found[-1]["name"] == "How to play"
    assert "How to play" not in choosable(troupe)
    # Every tag, once each, or the list has changed under the custodian.
    for wrong in (order[1:], [*order, order[0]]):
        refused = troupe.custodian.client.put("/blog/tag-order", json={"tag_ids": wrong})
        assert refused.status_code == 409


def test_every_change_is_in_the_audit_log(troupe: Troupe) -> None:
    c = troupe.custodian.client
    tags = kept(troupe)
    article(troupe, ["Community"])
    added = ok(c.post("/blog/tags", json={"name": "Elysium"}))[-1]
    ok(c.put(f"/blog/tags/{added['id']}", json={"name": "Elysium etiquette"}))
    ok(c.put(f"/blog/tags/{added['id']}/retired", json={"retired": True}))
    ok(c.put(f"/blog/tags/{added['id']}/retired", json={"retired": False}))
    ok(c.post(f"/blog/tags/{tags['Community']['id']}/merge", json={"into_id": added["id"]}))
    ids = [t["id"] for t in ok(c.get("/blog/tags/kept"))]
    ok(c.put("/blog/tag-order", json={"tag_ids": [ids[-1], *ids[:-1]]}))

    found = ok(c.get("/audit", params={"group": "blog"}))["entries"]

    messages = [e["message"] for e in reversed(found) if "tag" in e["action"]]
    assert messages[1:6] == [
        "custodian added the blog tag Elysium.",
        "custodian renamed the blog tag Elysium to Elysium etiquette.",
        "custodian retired the blog tag Elysium etiquette. It stays on the articles that have it.",
        "custodian brought back the blog tag Elysium etiquette.",
        "custodian merged the blog tag Community into Elysium etiquette, on 1 article.",
    ]
    assert messages[6].startswith(
        "custodian put the blog's tags in a new order: Elysium etiquette, How to play,"
    )
    levels = {e["action"]: e["level"] for e in found}
    assert levels["blog.tag_merged"] == "notice"
    assert levels["blog.tag_added"] == "info"
