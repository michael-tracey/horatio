"""Reading a troupe's characters from Yorick's Print Characters page (issue #482).

The page is Yorick's "Print Troupe Characters", saved from the browser as HTML with
its `_files/` folder. It holds three things this reads:

- the troupe's character list: each character's Yorick id (`backendid`), the name
  it is listed under, and its portrait thumbnail, if it has one;
- a printed sheet for each character: name, clan (with bloodline), archetype,
  antecedence, sect, faction and title; Physical, Social and Mental with their
  focuses; Morality; skills; and under headings, its backgrounds, disciplines,
  merits, flaws and the rest, one line each ("Haven x3", "Custom x1: Social Media",
  "Thaumaturgical Expertise (1, Path of Conjuring)");
- the disciplines it is in-clan for, where the player wrote them in the notes printed
  with the sheet, as "In clan: Animalism, Auspex, Presence" (#565). Yorick prints
  its extra in-clan disciplines nowhere else.

Blood, Willpower and health levels are printed too, but Horatio works them out from
the rest of the sheet, so they are not read. Nothing here knows Horatio's names for
traits: that is horatio.yorick_names.
"""

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

# The page (one of Yorick's single-page app's pages) holding the printed sheets.
PRINT_PAGE = "troupe-print-characters-all"
# Each printed sheet starts a new page when printed.
SHEET_CLASS = "force-printing-page-break"
# The portrait Yorick lists a character with when it has none of its own.
NO_PORTRAIT = "head_skull"
# A label Yorick's players put before a name: "[On hold] Agnes", "[NPC] Old Tom".
LABEL = re.compile(r"^\s*\[(?P<label>[^\]]*)\]\s*")
# A line of the printed notes naming the character's in-clan disciplines.
IN_CLAN = re.compile(r"^\s*in[\s-]*clan(?:\s+disciplines)?\s*:\s*(?P<names>.+)$", re.IGNORECASE)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}


class CannotRead(Exception):
    """The file is not a Print Characters page this can read; the message says why."""


# --- a small document tree ----------------------------------------------------------------


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    children: "list[Node | str]" = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def elements(self) -> "list[Node]":
        return [c for c in self.children if isinstance(c, Node)]

    def walk(self) -> "list[Node]":
        """This node and every element under it, in document order."""
        found: list[Node] = [self]
        for child in self.elements():
            found += child.walk()
        return found

    def find(self, tag: str | None = None, *, id: str | None = None) -> "Node | None":
        return next(
            (
                n
                for n in self.walk()[1:]
                if (tag is None or n.tag == tag) and (id is None or n.attrs.get("id") == id)
            ),
            None,
        )

    def find_all(self, tag: str) -> "list[Node]":
        return [n for n in self.walk()[1:] if n.tag == tag]

    def text(self) -> str:
        return " ".join(
            "".join(
                c if isinstance(c, str) else " " + c.text() + " " for c in self.children
            ).split()
        )


class TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {})
        self.open: list[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.open[-1].children.append(node)
        if tag not in VOID:
            self.open.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.open[-1].children.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        # Close up to the matching open element; a stray end tag closes nothing.
        for depth in range(len(self.open) - 1, 0, -1):
            if self.open[depth].tag == tag:
                del self.open[depth:]
                return

    def handle_data(self, data: str) -> None:
        self.open[-1].children.append(data)


def parse_html(text: str) -> Node:
    builder = TreeBuilder()
    builder.feed(text)
    builder.close()
    return builder.root


def lines_of(node: Node) -> list[tuple[str | None, str]]:
    """The node's text as lines, each with the heading (h4) it is under: a heading
    or a line break ends a line."""
    found: list[tuple[str | None, str]] = []
    heading: str | None = None
    current: list[str] = []

    def end() -> None:
        line = " ".join("".join(current).split())
        if line:
            found.append((heading, line))
        current.clear()

    def visit(n: Node) -> None:
        nonlocal heading
        for child in n.children:
            if isinstance(child, str):
                current.append(child)
            elif child.tag == "br":
                end()
            elif child.tag in ("h1", "h2", "h3", "h4"):
                end()
                heading = child.text()
            else:
                visit(child)

    visit(node)
    end()
    return found


# --- what a sheet holds -------------------------------------------------------------------


@dataclass
class Line:
    """One line of a printed sheet, as written: "Influences x4: The Elite" is the name
    "Influences", rated 4, with "The Elite" as its detail; "Arcane (1)" is the merit
    Arcane at 1 point. A line with no rating (a technique, a ritual, a lore) is its
    name alone."""

    text: str
    name: str
    rating: int | None = None
    detail: str = ""


RATED = re.compile(r"^(?P<name>.*?)\s+x(?P<rating>\d+)\s*(?::\s*(?P<detail>.*))?$")
POINTS = re.compile(r"^(?P<name>.*?)\s*\((?P<rating>-?\d+)\s*(?:,\s*(?P<detail>.*))?\)$")


def read_line(text: str, *, points: bool = False) -> Line:
    """A line as a name, rating and detail. With `points`, a merit, flaw or status:
    "Name (points, detail)"; otherwise "Name xN: detail"."""
    found = (POINTS if points else RATED).match(text)
    if found is None:
        return Line(text, text.strip())
    return Line(
        text,
        found["name"].strip(),
        int(found["rating"]),
        (found["detail"] or "").strip(),
    )


# Headings whose lines are written "Name (points, detail)".
POINTS_HEADINGS = {"Merits", "Flaws", "Status"}


@dataclass
class Attribute:
    rating: int
    # The focuses as printed, space-separated words, with any note after a colon.
    focuses: str


@dataclass
class PrintedCharacter:
    """One character as the page prints it."""

    # Yorick's id for the character, from the list; or, where the list has none for
    # its name, a stable hash of the name ("print-…").
    legacy_id: str
    # As printed, and without the label in brackets before it.
    printed_name: str
    name: str
    label: str
    # The portrait thumbnail's file, beside the page; None for none.
    portrait: str | None
    # Clan, Archetype, Sect, Faction, Title, Antecedence, as printed.
    identity: dict[str, str]
    attributes: dict[str, Attribute]
    # The Morality's name and rating: ("Humanity", 5), ("Scorched Heart", 2).
    morality: tuple[str, int] | None
    skills: list[Line]
    # The lines under each heading: Backgrounds, Haven, Disciplines, Merits...
    sections: dict[str, list[Line]]
    # What the player added to print with the sheet (notes, stat lines), as text.
    extended_text: str = ""
    # The in-clan disciplines its notes name, as written ("Animalism", "Thaumaturgy:
    # Path of Corruption"), the clan's own among them.
    in_clan: list[str] = field(default_factory=list[str])


def legacy_hash(name: str, occurrence: int = 1) -> str:
    """A stable id for a character the list gives no id for, from its printed name
    (and, for the second printed under one name, which one it is)."""
    text = name.strip().casefold() + (f"#{occurrence}" if occurrence > 1 else "")
    return "print-" + hashlib.sha256(text.encode()).hexdigest()[:16]


def split_label(printed: str) -> tuple[str, str]:
    """The name without a label such as "[On hold]", and the label. A name that is
    only a label ("[Pregen]") is the label's words."""
    found = LABEL.match(printed)
    if found is None:
        return printed.strip(), ""
    name = printed[found.end() :].strip()
    label = found["label"].strip()
    return name or label, label


def listed(root: Node) -> dict[str, list[tuple[str, str | None]]]:
    """The characters in the page's lists, by the name they are listed under: their
    Yorick ids and portraits."""
    found: dict[str, list[tuple[str, str | None]]] = {}
    for link in root.find_all("a"):
        if "character-list-item" not in link.classes or not link.attrs.get("backendid"):
            continue
        heading = link.find("h2")
        if heading is None:
            continue
        image = link.find("img")
        src = unquote(image.attrs.get("src", "")) if image is not None else ""
        portrait = src if src and NO_PORTRAIT not in src else None
        entry = (link.attrs["backendid"], portrait)
        names = found.setdefault(heading.text(), [])
        if entry not in names:
            names.append(entry)
    return found


def identity_of(sheet: Node) -> dict[str, str]:
    found: dict[str, str] = {}
    for bar in ("cpp-firstbar", "cpp-secondbar"):
        node = sheet.find(id=bar)
        if node is None:
            continue
        for heading in node.find_all("h2"):
            key, _, value = heading.text().partition(":")
            if value.strip():
                found[key.strip()] = value.strip()
    return found


def attributes_of(sheet: Node) -> dict[str, Attribute]:
    found: dict[str, Attribute] = {}
    node = sheet.find(id="cpp-attributes")
    if node is None:
        return found
    for heading, line in lines_of(node):
        if heading is None:
            continue
        if heading not in found:
            rating = re.match(r"\d+", line)
            found[heading] = Attribute(int(rating.group()) if rating else 0, "")
        elif not found[heading].focuses:
            found[heading].focuses = line
    return found


def morality_of(sheet: Node) -> tuple[str, int] | None:
    node = sheet.find(id="cpp-morality")
    if node is None:
        return None
    name = next((line for heading, line in lines_of(node) if heading == "Morality"), None)
    if name is None:
        return None
    # Each dot of Morality is an empty box.
    boxes = sum(1 for n in node.walk() if n.tag == "i" and "fa-square-o" in n.classes)
    return name, boxes


def skills_of(sheet: Node) -> list[Line]:
    node = sheet.find(id="cpp-skills")
    if node is None:
        return []
    return [
        read_line(n.text())
        for n in node.walk()
        if n.tag == "div" and "ui-body" in n.classes and n.text()
    ]


def sections_of(sheet: Node) -> dict[str, list[Line]]:
    found: dict[str, list[Line]] = {}
    for node in sheet.walk():
        if not node.attrs.get("id", "").startswith("cpp-bottom-"):
            continue
        for heading, line in lines_of(node):
            if heading is not None:
                found.setdefault(heading, []).append(
                    read_line(line, points=heading in POINTS_HEADINGS)
                )
    return found


def extended_text_of(sheet: Node) -> str:
    node = sheet.find(id="cpp-extended-print-text")
    return "\n".join(line for _, line in lines_of(node)) if node is not None else ""


def in_clan_of(extended_text: str) -> list[str]:
    """The disciplines an "In clan: A, B and C" line of the notes names, if one does."""
    for line in extended_text.splitlines():
        found = IN_CLAN.match(line)
        if found is not None:
            names = re.split(r",|;|/|\band\b|&", found["names"], flags=re.IGNORECASE)
            return [n.strip(" .") for n in names if n.strip(" .")]
    return []


def read_page(text: str) -> list[PrintedCharacter]:
    """Every character printed on the page, in the page's order."""
    root = parse_html(text)
    page = root.find(id=PRINT_PAGE)
    if page is None:
        raise CannotRead("This is not Yorick's Print Characters page: it has no printed sheets.")
    sheets = [n for n in page.walk() if n.tag == "div" and SHEET_CLASS in n.classes]
    if not sheets:
        raise CannotRead("The Print Characters page has no characters on it.")
    in_list = listed(root)
    found: list[PrintedCharacter] = []
    headed = [(sheet, header.text()) for sheet in sheets if (header := sheet.find(id="cpp-header"))]
    printed_names = Counter(printed for _, printed in headed)
    seen: Counter[str] = Counter()
    for sheet, printed in headed:
        if not printed:
            continue
        name, label = split_label(printed)
        seen[printed] += 1
        entries = in_list.get(printed, [])
        if len(entries) == 1 and printed_names[printed] == 1:
            legacy_id, portrait = entries[0]
        else:
            # Not in the list, or more than one character printed under the name: which
            # id and portrait is whose can't be told.
            legacy_id, portrait = legacy_hash(printed, seen[printed]), None
        extended_text = extended_text_of(sheet)
        found.append(
            PrintedCharacter(
                legacy_id=legacy_id,
                printed_name=printed,
                name=name,
                label=label,
                portrait=portrait,
                identity=identity_of(sheet),
                attributes=attributes_of(sheet),
                morality=morality_of(sheet),
                skills=skills_of(sheet),
                sections=sections_of(sheet),
                extended_text=extended_text,
                in_clan=in_clan_of(extended_text),
            )
        )
    return found


def read_file(path: Path) -> list[PrintedCharacter]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CannotRead(f"Cannot read {path}: {error}") from error
    return read_page(text)
