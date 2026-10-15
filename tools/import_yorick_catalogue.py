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
    # Free-text specialisations (a contact's name, a troupe's own option) are
    # "Custom" with the text as their detail.
    ("lore_specializations", "Custom"),
    ("academics_specializations", "Custom"),
    ("drive_specializations", "Custom"),
    ("linguistics_specializations", "Custom"),
    ("contacts_specializations", "Custom"),
    ("allies_specializations", "Custom"),
    ("influence_elite_specializations", "Custom"),
    ("influence_underworld_specializations", "Custom"),
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

# Ritual levels from the core book (Necromancy pp. 172-186, Thaumaturgy pp.
# 186-211): a ritual is bought at its level, for twice that in XP.
RITUAL_LEVELS = {
    "Necromancy: Bastone Diabolico": 4,
    "Necromancy: Black Blood": 2,
    "Necromancy: Chill of Oblivion": 5,
    "Necromancy: Lethe's Waters": 3,
    "Necromancy: Moldering Presence": 3,
    "Necromancy: Rise, Cerberus": 2,
    "Necromancy: Ritual of Xipe Totec": 4,
    "Necromancy: Scales of Maat": 2,
    "Necromancy: Spirit Beacon": 2,
    "Necromancy: Strength of Rotten Flesh": 4,
    "Necromancy: The Servant Undying": 3,
    "Necromancy: Weight of the Tomb": 5,
    "Thaumaturgy: Banish Big Brother": 2,
    "Thaumaturgy: Blood Contract": 5,
    "Thaumaturgy: Blood Mastery": 1,
    "Thaumaturgy: Burning Blade": 2,
    "Thaumaturgy: Cobra's Favor": 5,
    "Thaumaturgy: Craft Bloodstone": 2,
    "Thaumaturgy: Defense of the Sacred Haven": 1,
    "Thaumaturgy: Deflection of Wooden Doom": 1,
    "Thaumaturgy: Detect the Hidden Observer": 3,
    "Thaumaturgy: Engaging the Vessel of Transference": 1,
    "Thaumaturgy: Eyes of the Night Hawk": 2,
    "Thaumaturgy: Incorporeal Passage": 3,
    "Thaumaturgy: Mirror Walk": 3,
    "Thaumaturgy: Mirror of Second Sight": 3,
    "Thaumaturgy: Paper Flesh": 5,
    "Thaumaturgy: Pavis of the Foul Presence": 3,
    "Thaumaturgy: Recure of the Homeland": 2,
    "Thaumaturgy: Scry": 3,
    "Thaumaturgy: Severed Hand": 3,
    "Thaumaturgy: Shaft of Belated Quiescence": 3,
    "Thaumaturgy: Soul of the Homunculi": 3,
    "Thaumaturgy: Stone of the True Form": 5,
    "Thaumaturgy: Warding Circle": 1,
}

# Each clan"s merits, as the core book lists them (pp. 238-248), for merits whose
# Yorick requirement does not name the clan.
CLAN_MERITS = {
    "Assamite": [
        "Surprise Attack",
        "Bloodline: Vizier",
        "Awakening the Steel",
        "Bloodline: Sorcerer",
    ],
    "Brujah": [
        "Brotherhood",
        "Burning Wrath",
        "Scourge of Alecto",
        "Bloodline: True Brujah",
    ],
    "Followers of Set": [
        "Personal Cult",
        "Bloodline: Tlacique",
        "Bloodline: Vipers",
        "Addictive Blood",
        "Setite Sorcery",
    ],
    "Gangrel": [
        "Protean Blood",
        "Bloodline: Coyote",
        "Bloodline: Noiad",
        "Shape of the Beast's Wrath",
        "Bloodline: Ahrimanes",
    ],
    "Giovanni": [
        "Necromantic Expertise",
        "Mook",
        "Ghostly Retainer",
        "Bloodline: Premascine",
    ],
    "Lasombra": [
        "Angelic Visage",
        "Born in Shadow",
        "Walk the Abyss",
        "Bloodline: Kiasyd",
    ],
    "Malkavian": [
        "Expanded Consciousness",
        "Bloodline: Ananke",
        "Bloodline: Knights of the Moon",
        "Labyrinthine Mind",
        "Sophistry",
    ],
    "Nosferatu": [
        "Unseeing Eye",
        "Hidden Advantage",
        "Pliable Blood",
        "Unnatural Adaptation",
    ],
    "Toreador": [
        "Artist's Blessing",
        "Bloodline: Ishtarri",
        "Bloodline: Volgirre",
        "Absent Sway",
        "Dancer's Grace",
    ],
    "Tremere": [
        "Thaumaturgic Expertise",
        "Bloodline: Telyav",
        "Talisman",
        "Countermagic",
    ],
    "Tzimisce": [
        "Blood of the Tzimisce",
        "Szlachta",
        "Bloodline: Carpathian",
        "Bloodline: Koldun",
    ],
    "Ventrue": [
        "Aura of Command",
        "Bloodline: Crusader",
        "Paragon",
        "Regal Bearing",
    ],
    "Caitiff": [
        "Auspicious",
        "Eclipsed Blood",
        "Vestiges of Greatness",
    ],
    "Baali": [
        "Infernal Heritage",
        "Bloodline: Angelis Ater",
    ],
    "Cappadocians": [
        "Necromantic Insight",
        "Bloodline: Samedi",
        "Pierced Shroud",
        "Bloodline: Lamia",
    ],
    "Ravnos": [
        "Waking Dream",
        "Bloodline: Brahman",
        "Escape Artist",
    ],
    "Salubri": [
        "Righteous Fury",
        "Spiritual Armor",
        "Bloodline: Healer",
    ],
    "Daughters of Cacophony": [
        "Supernatural Aria",
        "Soaring Octaves",
    ],
    "Gargoyles": [
        "Flight",
        "Dark Statue",
    ],
}
CLAN_OF_MERIT = {merit: clan for clan, merits in CLAN_MERITS.items() for merit in merits}

# The areas both Influences cover, in place of Yorick's lists.
INFLUENCE_AREAS = [
    "Academics",
    "Activist Organizations",
    "Arts",
    "Commercial Industry",
    "Criminal Organizations",
    "Emergency Services",
    "Entertainment",
    "Finance",
    "High Society",
    "Infrastructure",
    "Law Enforcement",
    "Legal",
    "Local Government",
    "Manufacturing",
    "News Media",
    "Occult",
    "Religious Groups/Organizations",
    "Science/Medical",
    "Social Media",
    "Transportation",
]
INFLUENCE_CATEGORIES = ("influence_elite_specializations", "influence_underworld_specializations")

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
        if category in INFLUENCE_CATEGORIES:
            continue  # INFLUENCE_AREAS replaces these.
        seen.add((category, name))
        entries.append((category, name, row))
    for category in INFLUENCE_CATEGORIES:
        for name in INFLUENCE_AREAS:
            seen.add((category, name))
            entries.append((category, name, {}))
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
        elif category == "rituals" and name in RITUAL_LEVELS:
            properties.append(f"rating = {RITUAL_LEVELS[name]}")
        elif category in FIXED_RATING and row.get("value", "").strip().lstrip("-").isdigit():
            rating = BOOK_RATINGS.get((category, name), abs(int(row["value"])))
            properties.append(f"rating = {rating}")
        if category == "skills" and name in ATTRIBUTE_OF:
            properties.append(f"attribute = {toml_string(ATTRIBUTE_OF[name])}")
        for key in ("type", "requirement"):
            if "properties" in row:
                break  # Hand-written traits carry their own.
            if key == "requirement" and (category, name) in NOT_REQUIRED:
                continue
            value = REQUIREMENTS.get(row.get(key, "").strip(), row.get(key, "").strip())
            if category == "merits" and name in CLAN_OF_MERIT:
                if key == "requirement" and value in ("", "requires_specialization"):
                    value = CLAN_OF_MERIT[name]
                if key == "type" and not value:
                    value = "Clan"
            if value:
                properties.append(f"{key} = {toml_string(value)}")
        if properties:
            lines.append("properties = { " + ", ".join(properties) + " }")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(entries)} traits to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
