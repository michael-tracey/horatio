import { describe, expect, it } from "vitest";
import type { SireLineNodeOut, WebBondOut, WebPersonOut } from "../../api/types";
import type { StatLink, StatNode } from "../../boonStatistics";
import { DEFAULT_FILTERS, net, obligationWeb, personKey, summary, webClans, type Sources } from "./obligation";

// Three characters (Agnes, Bram, Cora), one NPC sire (Dmitri), and Old Marguerite,
// known only by name, written three ways across the layers.
const AGNES = "11111111-1111-7111-8111-111111111111";
const BRAM = "22222222-2222-7222-8222-222222222222";
const CORA = "33333333-3333-7333-8333-333333333333";
const DMITRI = "44444444-4444-7444-8444-444444444444";

const party = (key: string, name: string, more: Partial<StatNode["who"]> = {}): StatNode => ({
  who: { key, name, character_id: key.startsWith("name:") ? null : key, standing: key.startsWith("name:") ? null : "active", clan: null, age: null, sect: null, titles: [], ...more },
  owes: 0,
  owed: 0,
  net: 0,
  owes_count: 0,
  owed_count: 0,
});

const boonLink = (debtor: string, creditor: string, kinds: Record<string, number>): StatLink => ({
  debtor,
  creditor,
  count: Object.values(kinds).reduce((a, b) => a + b, 0),
  weight: 0,
  kinds,
});

const webPerson = (key: string, name: string, more: Partial<WebPersonOut> = {}): WebPersonOut => ({
  key,
  character_id: key.startsWith("name:") ? null : key,
  name,
  kind: key.startsWith("name:") ? null : "pc",
  clan: null,
  standing: "active",
  titles: [],
  ...more,
});

const bond = (thrall: string, regnant: string, level: number, status = "active"): WebBondOut => ({ id: `${thrall}>${regnant}`, thrall, regnant, level, status, fades_on: null });

const sireNode = (key: string, name: string, sire: string | null, more: Partial<SireLineNodeOut> = {}): SireLineNodeOut => ({
  key,
  character_id: key.startsWith("named:") ? null : key,
  name,
  clan: null,
  generation: null,
  left_reason: null,
  retired: false,
  kind: key.startsWith("named:") ? "named" : "pc",
  sire_key: sire,
  ...more,
});

const sources: Sources = {
  boons: {
    weights: { trivial: 0.5, minor: 1, major: 3, blood: 5, life: 10, defaults: true },
    nodes: [
      party(AGNES, "Agnes", { clan: "Toreador" }),
      party(BRAM, "Bram", { clan: "Ventrue", titles: ["Prince"] }),
      party("name:old marguerite", "old marguerite"),
    ],
    links: [boonLink(AGNES, BRAM, { major: 1, minor: 2 }), boonLink(BRAM, "name:old marguerite", { trivial: 1 })],
  },
  bonds: {
    people: [webPerson(AGNES, "Agnes", { clan: "Toreador" }), webPerson(BRAM, "Bram", { clan: "Ventrue", titles: ["Prince"] }), webPerson(CORA, "Cora", { standing: "off_field" }), webPerson("name:old marguerite", "Old Marguerite")],
    bonds: [bond(AGNES, BRAM, 3), bond(CORA, BRAM, 2), bond(BRAM, "name:old marguerite", 1, "broken")],
  },
  sires: {
    nodes: [
      sireNode(DMITRI, "Dmitri", null, { kind: "npc", clan: "Ventrue" }),
      sireNode(BRAM, "Bram", DMITRI, { clan: "Ventrue" }),
      sireNode("named:old marguerite|toreador", "Old Marguerite", null, { clan: "Toreador" }),
      sireNode(AGNES, "Agnes", "named:old marguerite|toreador", { clan: "Toreador" }),
    ],
  },
};

const everyone = { ...DEFAULT_FILTERS, who: "everyone" as const };

describe("the web of obligation", () => {
  it("lays every layer on one set of people: the same character from each source is one dot", () => {
    const web = obligationWeb(sources, everyone);
    expect(web.people.map((p) => p.name)).toEqual(["Agnes", "Bram", "Cora", "Dmitri", "Old Marguerite"]);
    expect(web.ties.map((t) => `${t.layer} ${t.from === AGNES ? "Agnes" : t.from}`)).toHaveLength(6);
    const bram = web.people.find((p) => p.key === BRAM)!;
    expect(bram).toMatchObject({ titles: ["Prince"], clan: "Ventrue", thralls: 2, boundTo: 0, sire: "Dmitri", owes: 0.5, owed: 5 });
  });

  it("joins a name only written differently in each layer", () => {
    const web = obligationWeb(sources, { ...everyone, endedBonds: true });
    const marguerite = web.people.filter((p) => p.name.toLowerCase() === "old marguerite");
    expect(marguerite).toHaveLength(1);
    expect(marguerite[0]).toMatchObject({ key: personKey(null, "Old Marguerite"), character_id: null, childer: 1, owed: 0.5 });
    // Its clan comes from the sire lines, where it was given one; the capitalised spelling wins.
    expect(marguerite[0]!.clan).toBe("Toreador");
    expect(marguerite[0]!.name).toBe("Old Marguerite");
  });

  it("switches each layer on and off", () => {
    const bondsOnly = obligationWeb(sources, { ...everyone, layers: new Set(["bonds"]) });
    expect(new Set(bondsOnly.ties.map((t) => t.layer))).toEqual(new Set(["bonds"]));
    expect(bondsOnly.people.map((p) => p.name)).toEqual(["Agnes", "Bram", "Cora"]);
    const none = obligationWeb(sources, { ...everyone, layers: new Set() });
    expect(none).toEqual({ people: [], ties: [] });
  });

  it("weighs boons with the troupe's weights and hides lighter ones when asked", () => {
    const web = obligationWeb(sources, { ...everyone, boonMinimum: 1 });
    const boons = web.ties.filter((t) => t.layer === "boons");
    expect(boons).toHaveLength(1);
    expect(boons[0]).toMatchObject({ from: AGNES, to: BRAM, weight: 5, count: 3, kind: "major" });
    expect(net(web.people.find((p) => p.key === AGNES)!)).toBe(-5);
  });

  it("keeps only those in play by default, and ended bonds only when asked", () => {
    const web = obligationWeb(sources, DEFAULT_FILTERS);
    expect(web.people.some((p) => p.name === "Cora")).toBe(false);
    expect(web.ties.some((t) => t.status === "broken")).toBe(false);
    const ended = obligationWeb(sources, { ...everyone, endedBonds: true });
    const broken = ended.ties.find((t) => t.status === "broken")!;
    expect(broken.open).toBe(false);
    // A broken bond holds nobody.
    expect(ended.people.find((p) => p.key === BRAM)!.boundTo).toBe(0);
  });

  it("filters by clan and title holders on either side", () => {
    const toreador = obligationWeb(sources, { ...everyone, clan: "Toreador" });
    const toreadors = [AGNES, personKey(null, "old marguerite")];
    expect(toreador.ties.length).toBeGreaterThan(0);
    expect(toreador.ties.every((t) => toreadors.includes(t.from) || toreadors.includes(t.to))).toBe(true);
    expect(toreador.ties.some((t) => t.from === CORA)).toBe(false);
    const court = obligationWeb(sources, { ...everyone, titled: true });
    expect(court.ties.every((t) => t.from === BRAM || t.to === BRAM)).toBe(true);
  });

  it("works with a layer missing, as when the troupe doesn't keep boons", () => {
    const web = obligationWeb({ sires: sources.sires }, everyone);
    expect(web.ties.map((t) => t.layer)).toEqual(["sires", "sires"]);
  });

  it("says every tie someone has, one line per layer", () => {
    const web = obligationWeb(sources, everyone);
    const bram = web.people.find((p) => p.key === BRAM)!;
    expect(summary(web, bram)).toEqual([
      { label: "boons", value: "owes 1 (0.5), is owed 3 (5)" },
      { label: "blood bonds", value: "2 thralls, bound to 0" },
      { label: "sire line", value: "sire Dmitri" },
    ]);
  });

  it("lists every clan in the sources for the filter, a bloodline under its clan", () => {
    expect(webClans(sources)).toEqual(["No clan", "Toreador", "Ventrue"]);
  });
});
