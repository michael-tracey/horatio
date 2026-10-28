"""Write the Vampire trait catalogue from a Yorick descriptions export.

    python3 tools/import_yorick_catalogue.py ../yorick/data/all_greensboro_descriptions_20260816.csv

Wrote backend/src/horatio/rules/data/bns_met_vampire_traits.toml. That file has
since been edited by hand (play counters, tags, the merits' and flaws' pages and
wording checked against the books, names spelt as the books spell them), so
running this again would undo that: it is kept as a record of the import.
"""

import csv
import json
import sys
import tomllib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend/src/horatio/rules/data/bns_met_vampire_traits.toml"
# Our own short descriptions for traits Yorick describes nowhere (skills, disciplines…).
DESCRIPTIONS = Path(__file__).resolve().parent / "vampire_descriptions.toml"

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
    "merits": "merits",
    "flaws": "flaws",
    "focus_mentals": "focus_mentals",
    "focus_socials": "focus_socials",
    "health_levels": "health_levels",
    "archetypes": "archetype",
    "sects": "sect",
    "factions": "faction",
}

# Sect status (Yorick's status_traits) is not imported: each status, with its sect
# and what it does, is written by hand in bns_met_vampire_status.toml.

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
    # Kineticism (Vol. 2, p. 72) is not in Yorick; the Inceptor merit lets a Caitiff pick it.
    ("extra_in_clan_disciplines", "Kineticism"),
]

# Where Yorick's values were one troupe's home rules rather than the book's, the
# catalogue follows the book (MET: Vampire The Masquerade core). A troupe that
# plays the home rules prices them with house rules instead.
# Traits for one sect only: a troupe that does not take that sect never sees them.
# The Rituals background is for initiated Sabbat (MET: VTM p. 452), and so are
# the ritae it teaches. (category, None) covers every trait in the category.
SECT_ONLY: dict[tuple[str, str | None], str] = {
    ("backgrounds", "Rituals"): "Sabbat",
    ("sabbat_rituals", None): "Sabbat",
}

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
    # MET: VTM Volume 2 Issue 1, p. 46.
    ("merits", "Inceptor"): 3,
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

# The clan and bloodline merits of MET: VTM Volume 2 Issue 1 ("Alternative Clan
# Merits", pp. 25-53) and Volume 2 ("Additional Bloodlines", pp. 31-64, and pp.
# 259-260), by the clan or bloodline (a clan entry in bns_met_vampire.toml) that
# may take them, under the catalogue's spelling. Ritual Master is both a Giovanni
# and a Tremere merit, so a check covers it instead.
SUPPLEMENT_CLAN_MERITS = {
    "Assamite": ["The Blade Whisper", "Bane's Blessing", "Web of Knives"],
    "Assamite: Vizier": ["Obsessive Study", "Blood Secrets", "Trials of the Blood"],
    "Assamite: Sorcerer": ["Thaumaturgically Gifted", "The Judge's Resilience", "Talismonger"],
    "Brujah": ["Breaking Point", "Iron Heart", "Fervent Iconoclast"],
    "Brujah: True Brujah": ["Timely Intervention", "Renaissance Mindset", "Borrowed Time"],
    "Followers of Set": ["Bane of the Aeons", "Shedding the Snake's Skin", "Voudoun Master"],
    "Followers of Set: Tlacique": ["The Heart of the Matter", "Blood Knows the Way", "Obsidian Claws"],
    "Followers of Set: Vipers": ["Serpentine Embrace", "Iron Scales", "Typhonic Beast"],
    "Gangrel": ["Seasoned Traveler", "Sanguine Indulgence", "Rending"],
    "Gangrel: Ahrimanes": ["Seekers of the Hidden", "Spirit Guide", "Sage of the Spirits"],
    "Gangrel: Coyote": ["The Man in Black", "Luck of the Damned", "Skullduggery"],
    "Gangrel: Noiad": ["Aquatic Predator", "Blood in the Water", "Sea Witch"],
    "Giovanni": ["Power Broker", "Soul Economy"],
    "Giovanni: Premascine": ["Death's Virtuoso", "Blood of the Ancients", "Scion of Death"],
    "Lasombra": ["Social Elite", "Trusted Confessor", "Flexible Morals"],
    "Lasombra: Kiasyd": ["Fae Blood", "Humble Abode", "The Friendly Folk"],
    "Malkavian": ["Strength of Madness", "Malkavian Time", "Method to the Madness"],
    "Malkavian: Ananke": ["Power Object", "Memento Mori", "Death Becomes You"],
    "Malkavian: Knights of the Moon": ["Quixotic", "Preternatural Awareness", "Madness Hunter"],
    "Nosferatu": ["Beneath Notice", "Painfully Shy", "Ardent Companion"],
    "Toreador": ["Immortal Beauty", "Greater Colors", "Ephemeral Rhapsody"],
    "Toreador: Ishtarri": ["Jack Be Nimble", "Master of Vice", "Itty Bitty Living Space"],
    "Toreador: Volgirre": ["Prodigy of the Flesh", "Visceral Artisan", "Old Habits"],
    "Tremere": ["Quick Caster", "Spellslinger"],
    "Tremere: Telyav": ["Ritual Supremacy", "Ritual Fluency", "Forge of the Soul"],
    "Tzimisce": ["Polymorphic Demeanor", "Emptiness of Faith", "Vozhd"],
    "Tzimisce: Carpathian": ["Knowledge is a Sword", "Flower of Kupala", "Scholomonariue"],
    "Tzimisce: Koldun": ["Kupala's Bounty", "No Place Like.Home", "Spiritual Animist"],
    "Ventrue": ["The Duty of Kings", "Ventrue Royalty", "Primacy of the Blood"],
    "Ventrue: Crusader": ["To the Manor Born", "Strength of Honor", "Hard as Steel"],
    "Caitiff": ["Adaptive", "Piece That Remains", "Inceptor"],
    "Baali": ["Subtle as Hell", "Moloch's Heir"],
    "Cappadocians": ["Chosen of Cappadocius", "Blood Deceit", "Not My Time"],
    "Cappadocians: Lamia": ["Beauty of the Beholder", "Not On My Watch", "Blessing of the Gorgons"],
    "Cappadocians: Samedi": ["Whispers from Beyond", "Walking Dead", "Loa's Rebirth"],
    "Ravnos": ["Mind Games", "Shady Dealings", "Jaded Existence"],
    "Ravnos: Brahman": ["Abstract Awareness", "Chimerical Templar", "Pierce the Veil"],
    # The Salubri warrior caste's; a check keeps them from the Healer bloodline.
    "Salubri": ["Sight Beyond Sight", "Demon Slayer", "Sanguine Anointing"],
    "Salubri: Healer": ["Lifegiver", "Touched by an Angel", "The Master's Path"],
    "Daughters of Cacophony": ["Rhythm of Battle", "Diva", "Songs Beyond Mortal Ken"],
    "Gargoyles": ["Arcane Branding", "Bonds of Stolen Vitae", "Art Imitates Life"],
    "Gangrel: Anda": ["All the Best Toys", "Dust in the Wind", "The Beast Within"],
    "Tzimisce: Bratovitch": ["Local Legends", "Become the Slasher", "Master of the Hounds"],
    "Lasombra: Corsairs": ["Rush of Battle", "Parley", "Abyssal Horror"],
    "Nosferatu: Creeps": ["Extrasensory Perceptions", "Fear Factor", "Shrinking Violet"],
}
# Volume 2's bloodline merits, for their parent clans (pp. 31-55).
BLOODLINE_MERIT_CLANS = {
    "Bloodline: Anda": "Gangrel",
    "Bloodline: Bratovitch": "Tzimisce",
    "Bloodline: Corsairs": "Lasombra",
    "Bloodline: Creeps": "Nosferatu",
}
CLAN_OF_MERIT = {
    **{merit: clan for clans in (CLAN_MERITS, SUPPLEMENT_CLAN_MERITS) for clan, merits in clans.items() for merit in merits},
    **BLOODLINE_MERIT_CLANS,
}

# Clan flaws Yorick names "Clan: Flaw" (Volume 2, "Alternative Clan Specific
# Flaws", pp. 268-286, and the Lhiannan and Nagaraja flaws, pp. 56-64): the clan
# each prefix means, where Yorick's spelling differs.
FLAW_PREFIX_CLANS = {
    "Cappadocian": "Cappadocians",
    "Daughters of Cacophany": "Daughters of Cacophony",
    "Gargoyle": "Gargoyles",
}

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
    # MET: VTM Volume 2.
    ("merits", "Dark Magics"): {
        "note": "A demonic pact teaches one path of Thaumaturgy, bought at out-of-clan costs; using it briefly taints your aura.",
        "page_reference": "Vol. 2, p. 259",
        "properties": {"rating": 3, "type": "Clan", "requirement": "Baali"},
    },
    ("merits", "Favored of the Decani"): {
        "note": "Once per game session, automatically succeed at a Daimoinon challenge, or turn a win into an exceptional success; your aura is stained for an hour.",
        "page_reference": "Vol. 2, p. 260",
        "properties": {"rating": 1, "type": "Clan", "requirement": "Baali: Angelis Ater"},
    },
    ("merits", "Song of the Fifth Trumpet"): {
        "note": "Mortals who see your Daimoinon powers are terrified into silence. You sense those who have made, or would make, infernal pacts.",
        "page_reference": "Vol. 2, p. 260",
        "properties": {"rating": 2, "type": "Clan", "requirement": "Baali: Angelis Ater"},
    },
    ("merits", "Shadows of the Past"): {
        "note": "Descended from the first Black Angels: in-clan disciplines are Daimoinon, Obtenebration and Dominate, plus up to 3 points of Lasombra merits free. Creation only.",
        "page_reference": "Vol. 2, p. 260",
        "properties": {"rating": 3, "type": "Clan", "requirement": "Baali: Angelis Ater"},
    },
    ("merits", "Blight of the Ever-Hungry"): {
        "note": "In-clan disciplines become Auspex, Potence and Necromancy: Path of the Graveborne; a serrated maw bites without a grapple. Creation only.",
        "page_reference": "Vol. 2, p. 62",
        "properties": {"rating": 3, "type": "Clan", "requirement": "Nagaraja"},
    },
    ("flaws", "Followers of Set: Temperament of Storms"): {
        "note": "Unless a storm is brewing or it is nearly dark, your difficulty to resist frenzy is increased by 2.",
        "page_reference": "Vol. 2, p. 271",
        "properties": {"rating": 2, "type": "Clan", "requirement": "Followers of Set"},
    },
    ("flaws", "Baali: Devil's Mark"): {
        "note": "A visible infernal deformity. Obfuscate can hide it but Vicissitude cannot remove it.",
        "page_reference": "Vol. 2, p. 281",
        "properties": {"rating": 1, "type": "Clan", "requirement": "Baali"},
    },
    ("flaws", "Baali: Carrion Comfort"): {
        "note": "You can feed only on the dead or carrion-eaters: no Herd, and an extra downtime action to feed or you start the game at half Blood.",
        "page_reference": "Vol. 2, p. 281",
        "properties": {"rating": 2, "type": "Clan", "requirement": "Baali"},
    },
    ("flaws", "Baali: Infernal Thrall"): {
        "note": "Indebted to a demon master as if you had Infernal Power, with none of its benefits; disobeying costs 5 aggravated damage.",
        "page_reference": "Vol. 2, p. 281",
        "properties": {"rating": 3, "type": "Clan", "requirement": "Baali"},
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
        "# are in bns_met_vampire.toml; sect status, and what each title gives, in",
        "# bns_met_vampire_status.toml.",
        "",
        "# Titles a troupe can give its characters; each troupe can add its own.",
        "titles = [",
        *[f"  {toml_string(t)}," for t in titles],
        "]",
        "",
    ]
    written = {
        (category, name): text
        for category, texts in tomllib.loads(DESCRIPTIONS.read_text(encoding="utf-8")).items()
        for name, text in texts.items()
    }
    unknown = set(written) - {(category, name) for category, name, _ in entries}
    if unknown:
        sys.exit(f"{DESCRIPTIONS.name} describes traits the catalogue lacks: {sorted(unknown)}")
    for category, name, row in entries:
        lines += ["[[traits]]", f"category = {toml_string(category)}", f"name = {toml_string(name)}"]
        note = row.get("note", "").strip() or written.get((category, name), "")
        if note:
            lines.append(f"description = {toml_string(note)}")
        if row.get("page_number", "").strip():
            lines.append(f"page_reference = {toml_string(row['page_number'].strip())}")
        properties: list[str] = []
        if "properties" in row:
            properties = [f"{k} = {json.dumps(v)}" for k, v in row["properties"].items()]
        elif category == "rituals" and row.get("value", "").strip().isdigit():
            # A ritual's level, which it is bought at. Yorick's values match the
            # books for every ritual: the core book (Necromancy pp. 181-186,
            # Thaumaturgy pp. 202-211) and MET: VTM Volume 2 (Abyss Mysticism
            # pp. 100-113, Necromancy pp. 133-147, Thaumaturgy pp. 163-183).
            properties.append(f"rating = {int(row['value'])}")
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
            if category == "flaws" and ": " in name and key == "requirement" and not value:
                prefix = name.split(": ")[0]
                value = FLAW_PREFIX_CLANS.get(prefix, prefix)
            if category == "merits" and name in CLAN_OF_MERIT:
                if key == "requirement" and value in ("", "requires_specialization"):
                    value = CLAN_OF_MERIT[name]
                if key == "type" and not value:
                    value = "Clan"
            if value:
                properties.append(f"{key} = {toml_string(value)}")
        sect = SECT_ONLY.get((category, name), SECT_ONLY.get((category, None)))
        if sect:
            properties.append(f"sect = {toml_string(sect)}")
        if properties:
            lines.append("properties = { " + ", ".join(properties) + " }")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(entries)} traits to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
