import { describe, expect, it } from "vitest";
import type { PlayView } from "../../api/types";
import { afterSending, incapacitated, itemsGoing, latestUndoable, loadQueue, makeTap, saveQueue, tapId, tapToast, withPending, type Tap } from "./tracker";

function view(overrides: Partial<PlayView> = {}): PlayView {
  return {
    character_id: "c1",
    character_name: "Agnes",
    player_name: "Jane",
    kind: "pc",
    blood_name: "Blood",
    panels: { beast: true, frenzy: true, morality: true, generation: true, feed: true },
    splat: "vampire",
    clan: "Brujah",
    sect: "Camarilla",
    generation: 1,
    blood_per_turn: 1,
    herd: 2,
    blood: { value: 10, most: 10, start: 10 },
    retainers: [],
    blood_usual: 10,
    half_blood: false,
    willpower: { value: 6, most: 6, start: 6 },
    health: {
      levels: [
        { name: "Healthy", boxes: 3 },
        { name: "Injured", boxes: 3 },
        { name: "Incapacitated", boxes: 3 },
      ],
      marks: [],
      stamina_focus: false,
    },
    morality: { name: "Humanity", value: 5, rating: 5 },
    beast: { value: 0, most: 5, start: 0 },
    derangements: { value: 0, most: 3, start: 0, least: 0, flaws: [], temporary: [] },
    expendables: [{ key: "trait:backgrounds/Herd/", name: "Herd", detail: "", group: "Backgrounds", uses: 2, left: 2, counter_id: null, owed: 0 }],
    equipment: [],
    equipped: [],
    influence: [],
    powers: [],
    game: null,
    log: [],
    ...overrides,
  };
}

const at = (minute: number) => new Date(Date.UTC(2026, 9, 17, 20, minute));
const change = (tracker: string, amount: number, minute: number, damage: "normal" | "aggravated" | null = null) =>
  makeTap({ kind: "change", tracker, amount, damage }, "g1", at(minute));

const ELITE = "trait:backgrounds/Influences: The Elite/";

function withElite(): PlayView {
  return view({
    expendables: [{ key: ELITE, name: "Influences: The Elite", detail: "", group: "Backgrounds", uses: 3, left: 3, counter_id: null, influence: "elite", owed: 0 }],
    influence: [
      {
        action_kind: "influence_elite",
        type: "elite",
        rating: 3,
        held: ["News Media"],
        options: ["News Media"],
        actions: [{ key: "no_party_crashers", name: "No Party Crashers", label: "5: No Party Crashers", level: 5, conflict: false }],
      },
    ],
  });
}

describe("influence spends", () => {
  it("read as the server reads them, with the details given", () => {
    const tap = makeTap(
      { kind: "change", tracker: ELITE, amount: -1, influence: { action: "no_party_crashers", specialization: "News Media", purpose: "To secure the Weather" } },
      "g1",
      at(1),
    );
    const shown = withPending(withElite(), [tap]);

    expect(shown.expendables[0]!.left).toBe(2);
    expect(shown.log[0]!.text).toBe("Elite: 5: No Party Crashers (News Media), To secure the Weather");
  });

  it("say when the details are still to come, and how many uses one spend took", () => {
    const shown = withPending(withElite(), [makeTap({ kind: "change", tracker: ELITE, amount: -2 }, "g1", at(1))]);

    expect(shown.log[0]!.text).toBe("Elite ×2: details to come");
  });

  it("read as any other counter where there is no troupe to log them in", () => {
    const shown = withPending({ ...withElite(), influence: [] }, [makeTap({ kind: "change", tracker: ELITE, amount: -1 }, "g1", at(1))]);

    expect(shown.log[0]!.text).toBe("Influences: The Elite 3 → 2");
  });
});

describe("withPending", () => {
  it("shows taps not yet sent on top of the server's view, newest first", () => {
    const shown = withPending(view(), [change("blood", -1, 1), change("trait:backgrounds/Herd/", -1, 2)]);

    expect(shown.blood.value).toBe(9);
    expect(shown.expendables[0]!.left).toBe(1);
    expect(shown.log.map((e) => e.text)).toEqual(["Herd 2 → 1", "Blood 10 → 9"]);
    expect(shown.log.every((e) => e.pending)).toBe(true);
  });

  it("names a Stock NPC's resource as its kind does, in Blood's place", () => {
    const shown = withPending(view({ blood_name: "Rage" }), [change("blood", -3, 1)]);

    expect(shown.blood.value).toBe(7);
    expect(shown.log[0]!.text).toBe("Rage 10 → 7");
  });

  it("never goes below nothing or above the most", () => {
    const shown = withPending(view(), [change("willpower", 3, 1), change("blood", -15, 2)]);

    expect(shown.willpower.value).toBe(6);
    expect(shown.blood.value).toBe(0);
  });

  it("keeps Derangement traits between 0 (1 for a Malkavian) and 3", () => {
    const shown = withPending(view(), [change("derangements", 2, 1), change("derangements", 2, 2)]);
    expect(shown.derangements.value).toBe(3);
    expect(shown.log.map((e) => e.text)).toEqual(["Derangement traits 2 → 3", "Derangement traits 0 → 2"]);

    const malkavian = view({ derangements: { value: 3, most: 3, start: 3, least: 1, flaws: [], temporary: [] } });
    expect(withPending(malkavian, [change("derangements", -3, 1)]).derangements.value).toBe(1);
  });

  it("adds a temporary derangement offline, and removes one the server has", () => {
    const fire = makeTap({ kind: "change", tracker: "derangement:d1", amount: 1, derangement: { name: "Phobia: fire", source: "Voice of Madness" } }, "g1", at(1));
    const added = withPending(view(), [fire]);
    expect(added.derangements.temporary).toEqual([{ key: "derangement:d1", name: "Phobia: fire", source: "Voice of Madness", held: true }]);
    expect(added.log[0]!.text).toBe("Temporary derangement added: Phobia: fire, from Voice of Madness");

    const saved = view({ derangements: { value: 0, most: 3, start: 0, least: 0, flaws: [], temporary: [{ key: "derangement:d2", name: "Paranoia", source: "", held: true }] } });
    const removed = withPending(saved, [change("derangement:d2", -1, 2)]);
    expect(removed.derangements.temporary[0]!.held).toBe(false);
    expect(removed.log[0]!.text).toBe("Temporary derangement removed: Paranoia");
    expect(saved.derangements.temporary[0]!.held).toBe(true);
  });

  it("marks health in order and heals the kind asked for", () => {
    const shown = withPending(view(), [change("health", 7, 1, "normal"), change("health", 1, 2, "aggravated"), change("health", -1, 3, "normal")]);

    expect(shown.health.marks).toEqual(["normal", "normal", "normal", "normal", "normal", "normal", "aggravated"]);
    expect(incapacitated(shown)).toBe(true);
    expect(incapacitated(view())).toBe(false);
  });

  it("leaves the server's view as it was", () => {
    const server = view();
    withPending(server, [change("blood", -1, 1), change("health", 1, 1, "normal")]);

    expect(server.blood.value).toBe(10);
    expect(server.health.marks).toEqual([]);
  });

  it("skips a waiting tap that a waiting undo takes back", () => {
    const spent = change("blood", -2, 1);
    const undo = makeTap({ kind: "undo", undoes: spent.id }, "g1", at(2));
    const shown = withPending(view(), [spent, undo]);

    expect(shown.blood.value).toBe(10);
    expect(shown.log.map((e) => [e.text, e.undone])).toEqual([
      ["Undid: Blood 10 → 8", false],
      ["Blood 10 → 8", true],
    ]);
  });

  it("takes back what a saved tap changed when undoing it offline", () => {
    const saved = view({
      blood: { value: 8, most: 10, start: 10 },
      log: [
        {
          id: "t1",
          kind: "change",
          tracker: "blood",
          amount: -2,
          damage: null,
          before: 10,
          after: 8,
          text: "Blood 10 → 8",
          note: "",
          happened_at: at(1).toISOString(),
          actor_name: "Jane",
          by_staff: false,
          undone: false,
          undoes: null,
        },
      ],
    });
    const shown = withPending(saved, [makeTap({ kind: "undo", undoes: "t1" }, "g1", at(2))]);

    expect(shown.blood.value).toBe(10);
    expect(shown.log[1]!.undone).toBe(true);
    expect(latestUndoable(shown.log)).toBeUndefined();
  });
});

describe("items given or discarded (#282)", () => {
  const give = makeTap({ kind: "change", tracker: "item:i1", amount: -1, equipment: { to_character_id: "c2", item_name: "Silver Dagger", to_name: "Bram" } }, null);
  const discard = makeTap({ kind: "change", tracker: "item:i2", amount: -1, note: "Into the river", equipment: { to_character_id: null, item_name: "Hunting rifle", to_name: "" } }, null);

  it("read in the log, and change no tracker", () => {
    const shown = withPending(view(), [give, discard]);
    expect(shown.log.map((e) => e.text)).toEqual(["Discarded Hunting rifle", "Gave Silver Dagger to Bram"]);
    expect(shown.blood).toEqual(view().blood);
    expect(itemsGoing(shown.log)).toEqual(new Set(["i1", "i2"]));
  });

  it("come back to the tab when undone before they are sent", () => {
    const shown = withPending(view(), [give, discard, makeTap({ kind: "undo", undoes: give.id }, null)]);
    expect(shown.log[0]!.text).toBe("Undid: Gave Silver Dagger to Bram");
    expect(itemsGoing(shown.log)).toEqual(new Set(["i2"]));
  });
});

describe("items equipped (#306)", () => {
  const item = (id: string, name: string, kind: string, hands: number | null = null) => ({ id, name, kind, hands, modifiers: [] });
  const items = [item("i1", "Silver Dagger", "melee", 1), item("i2", "Flak Vest", "protective"), item("i3", "Chain Mail", "protective")];
  const equip = (id: string, amount = 1, minute = 0) => makeTap({ kind: "change", tracker: `equip:${id}`, amount }, null, at(minute));

  it("show at once, with what each puts away, kept for Undo", () => {
    const shown = withPending(view({ equipment: items, equipped: ["i2"] }), [equip("i1"), equip("i3", 1, 1)]);
    expect(shown.equipped).toEqual(["i1", "i3"]);
    expect(shown.log.map((e) => e.text)).toEqual(["Equipped Chain Mail: took off Flak Vest (one worn at a time)", "Equipped Silver Dagger"]);
    const dagger = equip("i1");
    const undone = withPending(view({ equipment: items }), [dagger, makeTap({ kind: "undo", undoes: dagger.id }, null, at(2))]);
    expect(undone.equipped).toEqual([]);
  });

  it("go once given or discarded", () => {
    const give = makeTap({ kind: "change", tracker: "item:i1", amount: -1, equipment: { to_character_id: "c2", item_name: "Silver Dagger", to_name: "Bram" } }, null, at(1));
    const shown = withPending(view({ equipment: items, equipped: ["i1", "i2"] }), [give]);
    expect(shown.equipped).toEqual(["i2"]);
    expect(shown.equipment.map((i) => i.name)).toEqual(["Flak Vest", "Chain Mail"]);
  });
});

describe("latestUndoable", () => {
  it("is the newest tap not undone and not itself an undo", () => {
    const shown = withPending(view(), [change("blood", -1, 1), makeTap({ kind: "note", note: "fed at the club" }, "g1", at(2))]);

    expect(latestUndoable(shown.log)?.text).toBe("Note");
  });
});

describe("tapToast (#358)", () => {
  it("says what a tap did and where the tracker stands, worded apart from the log", () => {
    const shown = withPending(view(), []);
    const spend = change("blood", -1, 1);

    expect(tapToast(shown, spend)).toBe("Spent 1 Blood · 9/10");
    expect(withPending(view(), [spend]).log[0]!.text).toBe("Blood 10 → 9");
    expect(tapToast(shown, change("willpower", 1, 1))).toBe("Restored 1 Willpower · 6/6");
    expect(tapToast(shown, change("health", 1, 1, "aggravated"))).toBe("Took 1 aggravated · 1/9 marked");
    expect(tapToast(shown, change("morality", -1, 1))).toBe("Humanity −1 · 4/5");
    expect(tapToast(shown, change("beast", 1, 1))).toBe("Beast traits +1 · 1/5");
    expect(tapToast(shown, change("trait:backgrounds/Herd/", -1, 1))).toBe("Used 1 Herd · 1 of 2 left");
    expect(tapToast(shown, makeTap({ kind: "note", note: "fed" }, "g1", at(1)))).toBe("Note added");
  });

  it("says where an undone tap left the tracker, waiting or saved", () => {
    const spend = change("blood", -1, 1);
    const waiting = withPending(view(), [spend]);
    expect(tapToast(waiting, makeTap({ kind: "undo", undoes: spend.id }, "g1", at(2)))).toBe("Undone · Blood 10/10");

    const { pending: _, ...entry } = waiting.log[0]!;
    const saved = view({ blood: { value: 9, most: 10, start: 10 }, log: [entry] });
    expect(tapToast(withPending(saved, []), makeTap({ kind: "undo", undoes: spend.id }, "g1", at(2)))).toBe("Undone · Blood 10/10");
  });
});

describe("the queue on the device", () => {
  function memory(): Storage {
    const data = new Map<string, string>();
    return {
      get length() {
        return data.size;
      },
      clear: () => data.clear(),
      getItem: (k) => data.get(k) ?? null,
      key: (i) => [...data.keys()][i] ?? null,
      removeItem: (k) => void data.delete(k),
      setItem: (k, v) => void data.set(k, v),
    };
  }

  it("keeps taps per character until they are sent", () => {
    const storage = memory();
    const taps = [change("blood", -1, 1), change("blood", -1, 2)];
    saveQueue("c1", taps, storage);

    expect(loadQueue("c1", storage)).toEqual(taps);
    expect(loadQueue("c2", storage)).toEqual([]);

    // A tap made while the first batch was on its way stays.
    const later = change("willpower", -1, 3);
    const left = afterSending([...taps, later], taps);
    expect(left).toEqual([later]);
    saveQueue("c1", [], storage);
    expect(storage.length).toBe(0);
  });

  it("survives storage that throws or holds rubbish", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(loadQueue("c1", broken)).toEqual([]);
    expect(() => saveQueue("c1", [change("blood", -1, 1)], broken)).not.toThrow();

    const storage = memory();
    storage.setItem("horatio.play.c1", "{not json");
    expect(loadQueue("c1", storage)).toEqual([]);
  });
});

describe("makeTap", () => {
  it("stamps the time it happened and the game, with a fresh id", () => {
    const tap: Tap = makeTap({ kind: "change", tracker: "blood", amount: -1, note: "  fed  " }, "g1", at(5));

    expect(tap.happened_at).toBe("2026-10-17T20:05:00.000Z");
    expect(tap.game_id).toBe("g1");
    expect(tap.note).toBe("fed");
    expect(tap.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(tapId()).not.toBe(tapId());
  });
});

describe("makeTap with an id chosen ahead", () => {
  it("keeps the id, so feeding's tap is the same tap however often it is made", () => {
    const id = tapId();
    expect(makeTap({ id, kind: "change", tracker: "blood", amount: 2 }, "g1", at(5)).id).toBe(id);
  });
});

describe("a ghoul's vitae (MET: VtM core p. 297)", () => {
  const ghoul = () =>
    view({
      splat: "ghoul",
      blood_name: "Vitae",
      panels: { beast: false, frenzy: false, morality: false, generation: false, feed: false },
      generation: 0,
      blood: { value: 2, most: 5, start: 2 },
      blood_usual: 5,
      beast: { value: 0, most: 5, start: 0 },
      morality: null,
      vitae: { pool: 10, human: 8, human_start: 8, last_drank_at: null, days: 30 },
    });

  it("spends vitae but never human Blood, and Beast traits are not on the sheet", () => {
    const shown = withPending(ghoul(), [makeTap({ kind: "change", tracker: "blood", amount: -1 }, null), makeTap({ kind: "change", tracker: "beast", amount: 1 }, null)]);
    expect(shown.blood.value).toBe(1);
    expect(shown.vitae!.human).toBe(8);
    expect(shown.beast.value).toBe(0);
    expect(shown.log.map((e) => e.text)).toEqual(["Beast traits +1", "Vitae 2 → 1"]);
  });

  it("drinks up to 5, turning human Blood to vitae in a full pool", () => {
    const shown = withPending(ghoul(), [makeTap({ kind: "change", tracker: "drank", amount: 5 }, null)]);
    expect(shown.blood.value).toBe(5);
    expect(shown.vitae!.human).toBe(5);
    expect(shown.log[0]!.text).toBe("Drank 5 vitae: Vitae 2 → 5");
  });

  it("is not a vampire's to drink", () => {
    const shown = withPending(view(), [makeTap({ kind: "change", tracker: "drank", amount: 2 }, null)]);
    expect(shown.blood.value).toBe(10);
  });
});

describe("spending sect status (issue #253)", () => {
  const carried = (key: string, name: string, type: string, spent = false) => ({
    key,
    name,
    type,
    source: type === "Fleeting" ? "Prince Varga" : "Prince",
    about: null,
    spendable: true,
    spent,
    spent_by: spent ? "t0" : null,
    suppressed: false,
    place: "",
    story: "",
  });
  const withStatus = (spent = false): PlayView =>
    view({
      status: {
        sect: "Camarilla",
        accepted: "Acknowledged",
        troupe_id: "t1",
        troupe_name: "Court",
        sources: [],
        source: "Prince",
        source_chosen: false,
        choosing: false,
        conditions: [],
        titles: [],
        carried: [carried("status:Authority", "Authority", "Abiding", spent), carried("held:h1", "Loyal", "Fleeting")],
        fleeting_cap: 5,
        cap_why: [],
        outsider_sect: null,
        outsider_through: null,
        suppressed: [],
      },
    });

  it("greys out a status spent for the game until its Undo", () => {
    const spend = change("status:Authority", -1, 1);
    const shown = withPending(withStatus(), [spend]);
    const authority = shown.status!.carried[0]!;
    expect([authority.spent, authority.spent_by]).toEqual([true, spend.id]);
    expect(shown.log[0]!.text).toBe("Spent Authority");

    const undone = withPending(withStatus(), [spend, makeTap({ kind: "undo", undoes: spend.id }, "g1", at(2))]);
    expect(undone.status!.carried[0]!.spent).toBe(false);
  });

  it("spends a fleeting status for good", () => {
    const shown = withPending(withStatus(), [change("held:h1", -1, 1)]);
    expect(shown.status!.carried[1]!.spent).toBe(true);
    expect(shown.log[0]!.text).toBe("Spent Loyal for good");
  });

  it("gives back a saved spend undone offline", () => {
    const saved = withStatus(true);
    saved.log = [
      {
        id: "t0",
        kind: "change",
        tracker: "status:Authority",
        amount: -1,
        damage: null,
        before: 1,
        after: 0,
        text: "Spent Authority",
        note: "",
        happened_at: at(1).toISOString(),
        actor_name: "Jane",
        by_staff: false,
        undone: false,
        undoes: null,
      },
    ];
    const shown = withPending(saved, [makeTap({ kind: "undo", undoes: "t0" }, "g1", at(2))]);
    expect(shown.status!.carried[0]!.spent).toBe(false);
  });
});
