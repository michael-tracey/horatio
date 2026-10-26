import { describe, expect, it } from "vitest";
import type { PlayView } from "../../api/types";
import { afterSending, incapacitated, latestUndoable, loadQueue, makeTap, saveQueue, tapId, withPending, type Tap } from "./tracker";

function view(overrides: Partial<PlayView> = {}): PlayView {
  return {
    character_id: "c1",
    character_name: "Agnes",
    player_name: "Jane",
    kind: "pc",
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

describe("latestUndoable", () => {
  it("is the newest tap not undone and not itself an undo", () => {
    const shown = withPending(view(), [change("blood", -1, 1), makeTap({ kind: "note", note: "fed at the club" }, "g1", at(2))]);

    expect(latestUndoable(shown.log)?.text).toBe("Note");
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
