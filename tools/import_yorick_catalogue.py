"""Write the Vampire trait catalogue from a Yorick descriptions export.

    python3 tools/import_yorick_catalogue.py ../yorick/data/all_greensboro_descriptions_20260816.csv

Writes backend/src/horatio/rules/data/bns_met_vampire_traits.toml. Re-run it
to refresh the catalogue; edit that file by hand only for traits Yorick never
had.
"""

import csv
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend/src/horatio/rules/data/bns_met_vampire_traits.toml"

# Yorick category -> Horatio category, for the Vampire categories.
CATEGORIES = {
    "skills": "skills",
    "lore_specializations": "lore_specializations",
    "academics_specializations": "academics_specializations",
    "drive_specializations": "drive_specializations",
    "linguistics_specializations": "linguistics_specializations",
    "disciplines": "disciplines",
    "techniques": "techniques",
    "elder_disciplines": "elder_disciplines",
    "luminary_disciplines": "luminary_disciplines",
    "rituals": "rituals",
    "extra_in_clan_disciplines": "extra_in_clan_disciplines",
    "paths": "paths",
    "backgrounds": "backgrounds",
    "haven_specializations": "haven_specializations",
    "sabbat_rituals": "sabbat_rituals",
    "vampiric_texts": "vampiric_texts",
    "influence_elite_specializations": "influence_elite_specializations",
    "influence_underworld_specializations": "influence_underworld_specializations",
    "status_traits": "status_traits",
    "merits": "merits",
    "flaws": "flaws",
    "focus_mentals": "focus_mentals",
    "focus_socials": "focus_socials",
    "health_levels": "health_levels",
    "archetypes": "archetype",
    "sects": "sect",
    "factions": "faction",
}

# Traits Yorick seeded in code rather than in its descriptions table.
EXTRA = [
    ("attributes", "Physical"),
    ("attributes", "Social"),
    ("attributes", "Mental"),
    ("focus_physicals", "Strength"),
    ("focus_physicals", "Dexterity"),
    ("focus_physicals", "Stamina"),
    ("willpower_sources", "Willpower"),
]

# Where Yorick's values were one troupe's home rules rather than the book's, the
# catalogue follows the book (MET: Vampire The Masquerade core). A troupe that
# plays the home rules prices them with house rules instead.
BOOK_RATINGS = {
    ("merits", "Absent Sway"): 3,
    ("merits", "Addictive Blood"): 3,
    ("merits", "Countermagic"): 4,
    ("merits", "Dancer's Grace"): 4,
    ("merits", "Labyrinthine Mind"): 3,
    ("merits", "Regal Bearing"): 4,
    ("merits", "Setite Sorcery"): 4,
    ("merits", "Sophistry"): 4,
    ("merits", "Talisman"): 3,
    ("merits", "Unnatural Adaptation"): 4,
}

# Spelling fixes to Yorick's requirement column.
REQUIREMENTS = {"Follower of Set": "Followers of Set"}

# Requirements Yorick recorded that the book does not make: Weak Stomach only
# hits Neonates harder (p. 266); anyone can take it.
NOT_REQUIRED = {("flaws", "Weak Stomach")}

# Book traits Yorick never had, with their properties.
EXTRA_TRAITS = {
    ("merits", "Blood of the Tzimisce"): {
        "page_reference": "244",
        "properties": {"rating": 1, "type": "Clan", "requirement": "Tzimisce"},
    },
    ("merits", "Path of Harmony"): {
        "page_reference": "256",
        "properties": {"rating": 3, "type": "Morality"},
    },
    ("paths", "Harmony"): {"page_reference": "256", "properties": {}},
    ("merits", "Thaumaturgic Expertise"): {
        "page_reference": "243",
        "properties": {"rating": 1, "type": "Clan", "requirement": "Tremere"},
    },
}

# Which attribute each skill generally goes with, for grouping skills on screen.
# Yorick never recorded this; it is the usual split, kept here to be corrected.
SKILL_ATTRIBUTES = {
    "Physical": [
        "Athletics", "Brawl", "Dodge", "Drive", "Firearms", "Melee", "Security", "Stealth",
        "Survival",
    ],
    "Social": [
        "Animal Ken", "Empathy", "Intimidation", "Leadership", "Performance", "Streetwise",
        "Subterfuge",
    ],
    "Mental": [
        "Academics", "Awareness", "Computer", "Crafts", "Investigation", "Linguistics", "Lore",
        "Medicine", "Occult", "Science",
    ],
}
ATTRIBUTE_OF = {skill: attr for attr, skills in SKILL_ATTRIBUTES.items() for skill in skills}

# Merits and flaws are bought at their point value, never another rating.
FIXED_RATING = {"merits", "flaws"}


def toml_string(value: str) -> str:
    # JSON string escaping is valid TOML basic-string escaping.
    return json.dumps(value, ensure_ascii=False)


def main(csv_path: str) -> None:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    seen: set[tuple[str, str]] = set()
    entries: list[tuple[str, str, dict[str, str]]] = []
    for row in sorted(rows, key=lambda r: (r["category"], r["name"])):
        category = CATEGORIES.get(row["category"])
        name = row["name"].strip()
        if category is None or not name or (category, name) in seen:
            continue
        seen.add((category, name))
        entries.append((category, name, row))
    for category, name in EXTRA:
        if (category, name) not in seen:
            seen.add((category, name))
            entries.append((category, name, {}))
    for (category, name), extra in EXTRA_TRAITS.items():
        if (category, name) not in seen:
            seen.add((category, name))
            entries.append((category, name, {"page_number": extra["page_reference"], **extra}))

    titles = sorted({r["name"].strip() for r in rows if r["category"] == "titles" and r["name"].strip()})
    lines = [
        "# The Vampire trait catalogue, generated by tools/import_yorick_catalogue.py",
        "# from a Yorick descriptions export. Clans, with their in-clan disciplines,",
        "# are in bns_met_vampire.toml.",
        "",
        "# Titles a troupe can give its characters; each troupe can add its own.",
        "titles = [",
        *[f"  {toml_string(t)}," for t in titles],
        "]",
        "",
    ]
    for category, name, row in entries:
        lines += ["[[traits]]", f"category = {toml_string(category)}", f"name = {toml_string(name)}"]
        if row.get("note", "").strip():
            lines.append(f"description = {toml_string(row['note'].strip())}")
        if row.get("page_number", "").strip():
            lines.append(f"page_reference = {toml_string(row['page_number'].strip())}")
        properties: list[str] = []
        if "properties" in row:
            properties = [f"{k} = {json.dumps(v)}" for k, v in row["properties"].items()]
        elif category in FIXED_RATING and row.get("value", "").strip().lstrip("-").isdigit():
            rating = BOOK_RATINGS.get((category, name), abs(int(row["value"])))
            properties.append(f"rating = {rating}")
        if category == "skills" and name in ATTRIBUTE_OF:
            properties.append(f"attribute = {toml_string(ATTRIBUTE_OF[name])}")
        for key in ("type", "requirement"):
            if key == "requirement" and (category, name) in NOT_REQUIRED:
                continue
            if row.get(key, "").strip():
                value = row[key].strip()
                properties.append(f"{key} = {toml_string(REQUIREMENTS.get(value, value))}")
        if properties:
            lines.append("properties = { " + ", ".join(properties) + " }")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(entries)} traits to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
