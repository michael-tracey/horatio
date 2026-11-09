"""A character's printable sheet as one plain HTML file, for a backup (issue #567): what
the print view shows (horatio.api.printing), readable in any browser without Horatio.
Self-contained: its styles are in it, and its picture, if any, is in it or beside it."""

from html import escape

from horatio.api.printing import PrintedSheet, PrintedTrait

STYLE = """
body { font-family: Georgia, serif; color: #111; background: #fff; max-width: 52rem;
  margin: 1.5rem auto; padding: 0 1rem; line-height: 1.4; }
header { display: flex; gap: 1rem; align-items: center; border-bottom: 2px solid #111;
  padding-bottom: .5rem; margin-bottom: 1rem; }
header img { width: 96px; height: 96px; object-fit: cover; border-radius: 4px; }
h1 { margin: 0; font-size: 1.8rem; }
h2 { font-size: 1.1rem; border-bottom: 1px solid #999; margin: 1.2rem 0 .4rem; }
h3 { font-size: .95rem; margin: .6rem 0 .2rem; }
.meta { color: #444; font-size: .9rem; }
.columns { columns: 2 16rem; column-gap: 2rem; }
.category { break-inside: avoid; }
ul { list-style: none; padding: 0; margin: 0; }
li { display: flex; justify-content: space-between; gap: 1rem; font-size: .95rem; }
.dots { letter-spacing: .1em; white-space: nowrap; }
.note { color: #555; font-size: .85rem; }
footer { margin-top: 2rem; color: #666; font-size: .8rem; }
@media print { body { margin: 0; } }
"""


def dots(rating: int | None) -> str:
    if rating is None:
        return ""
    if rating > 10:
        return str(rating)
    return "●" * rating + "○" * max(0, 5 - rating)


def trait_line(trait: PrintedTrait) -> str:
    name = escape(trait.name + (f" ({trait.detail})" if trait.detail else ""))
    if trait.house:
        name += " ★"
    waiting = (
        f' <span class="note">(waiting from {trait.pending_from})</span>'
        if trait.pending_from is not None
        else ""
    )
    return f'<li><span>{name}{waiting}</span><span class="dots">{dots(trait.rating)}</span></li>'


def grouped(traits: list[PrintedTrait]) -> list[tuple[str, list[tuple[str, list[PrintedTrait]]]]]:
    """The traits by group, then category, in the order the sheet has them."""
    groups: list[tuple[str, list[tuple[str, list[PrintedTrait]]]]] = []
    for trait in traits:
        if not groups or groups[-1][0] != trait.group:
            groups.append((trait.group, []))
        categories = groups[-1][1]
        if not categories or categories[-1][0] != trait.category_name:
            categories.append((trait.category_name, []))
        categories[-1][1].append(trait)
    return groups


def sheet_html(sheet: PrintedSheet, picture: str | None = None, exported_on: str = "") -> str:
    """The sheet as an HTML page. `picture` is the portrait's address: a file beside
    it, or a data: URL."""
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(sheet.character_name)}</title>",
        f"<style>{STYLE}</style></head><body>",
        "<header>",
    ]
    if picture:
        parts.append(f'<img src="{escape(picture, quote=True)}" alt="">')
    meta = [sheet.splat.capitalize(), f"Player: {sheet.player_name}"]
    if sheet.troupe_name:
        meta.append(("Home troupe: " if sheet.home else "Troupe: ") + sheet.troupe_name)
    if sheet.domitor:
        meta.append(f"Domitor: {sheet.domitor}")
    parts.append(
        f"<div><h1>{escape(sheet.character_name)}</h1>"
        f'<div class="meta">{" · ".join(escape(m) for m in meta)}</div>'
    )
    if sheet.titles:
        parts.append(f'<div class="meta">Titles: {escape(", ".join(sheet.titles))}</div>')
    if sheet.status:
        parts.append(f'<div class="meta">Status: {escape(", ".join(sheet.status))}</div>')
    parts.append("</div></header>")

    for group, categories in grouped(sheet.traits):
        parts.append(f"<h2>{escape(group)}</h2><div class='columns'>")
        for category, traits in categories:
            parts.append(f'<div class="category"><h3>{escape(category)}</h3><ul>')
            parts += [trait_line(t) for t in traits]
            parts.append("</ul></div>")
        parts.append("</div>")

    blood = f"{sheet.blood.most}, {sheet.blood.per_turn} a turn"
    if sheet.blood.pool is not None:
        blood += f" (of a pool of {sheet.blood.pool})"
    parts.append(f"<h2>Blood</h2><p>{escape(blood)}</p>")
    if sheet.diablerie:
        days = ", ".join(d.isoformat() for d in sheet.diablerie)
        parts.append(f"<p>Diablerie: {escape(days)}</p>")

    if sheet.retainers:
        parts.append("<h2>Retainers</h2><ul>")
        for r in sheet.retainers:
            about = f' <span class="note">{escape(r.description)}</span>' if r.description else ""
            lost = f' <span class="note">({escape(r.lost)})</span>' if r.lost else ""
            parts.append(
                f"<li><span>{escape(r.name or 'Unnamed')}{lost}{about}</span>"
                f'<span class="dots">{dots(r.dots)}</span></li>'
            )
        parts.append("</ul>")
    named = [i for i in sheet.identities if i.name]
    if named:
        parts.append("<h2>Alternate Identities</h2><ul>")
        for i in named:
            accepted = f" (accepted by {i.accepted_by})" if i.accepted_by else ""
            parts.append(
                f"<li><span>{escape(i.name + accepted)}</span>"
                f'<span class="dots">{dots(i.dots)}</span></li>'
            )
        parts.append("</ul>")
    if sheet.equipment:
        parts.append("<h2>Equipment</h2><ul>")
        for item in sheet.equipment:
            qualities = ", ".join(
                q.name + (f" ({q.detail})" if q.detail else "") for q in item.qualities
            )
            facts = f"{item.kind_name}, {item.grade}" + (f": {qualities}" if qualities else "")
            note = f'<span class="note">{escape(facts)}</span>'
            parts.append(f"<li><span>{escape(item.name)} {note}</span></li>")
        parts.append("</ul>")
    if sheet.wording:
        parts.append("<h2>House wording</h2>")
        for w in sheet.wording:
            page = f" ({w.page})" if w.page else ""
            parts.append(f"<h3>{escape(w.name + page)}</h3><p>{escape(w.text)}</p>")
    footer = "Exported from Horatio" + (f" on {exported_on}" if exported_on else "")
    parts.append(f"<footer>{escape(footer)}.</footer></body></html>")
    return "\n".join(parts) + "\n"
