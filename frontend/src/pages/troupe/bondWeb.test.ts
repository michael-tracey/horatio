import { describe, expect, it } from "vitest";
import type { WebBondOut, WebPersonOut } from "../../api/types";
import { bondWeb, chains, DEFAULT_FILTERS, mostThralls, standingText, webClans } from "./bondWeb";

const person = (key: string, more: Partial<WebPersonOut> = {}): WebPersonOut => ({
  key,
  character_id: key.startsWith("name:") ? null : key,
  name: more.name ?? key.replace("name:", ""),
  kind: key.startsWith("name:") ? null : "pc",
  clan: null,
  standing: "active",
  titles: [],
  ...more,
});

const bond = (thrall: string, regnant: string, level = 1, status = "active"): WebBondOut => ({
  id: `${thrall}>${regnant}`,
  thrall,
  regnant,
  level,
  status,
  fades_on: null,
});

const people = [
  person("agnes", { clan: "Toreador" }),
  person("bram", { clan: "Ventrue", titles: ["Prince"] }),
  person("cora", { clan: "Gangrel: Coyote", standing: "off_field" }),
  person("name:old marguerite", { name: "Old Marguerite" }),
  person("dmitri", { clan: "Ventrue" }),
];

const bonds = [
  bond("agnes", "bram", 3),
  bond("bram", "name:old marguerite", 2),
  bond("cora", "bram", 1),
  bond("dmitri", "bram", 2, "fading"),
  bond("agnes", "dmitri", 1, "broken"),
];

describe("the web of blood bonds", () => {
  it("keeps the bonds still felt among those in play, with everyone on either side", () => {
    const web = bondWeb({ people, bonds }, DEFAULT_FILTERS);
    expect(web.links.map((l) => l.id)).toEqual(["agnes>bram", "bram>name:old marguerite", "dmitri>bram"]);
    expect(web.nodes.map((n) => n.name)).toEqual(["agnes", "bram", "dmitri", "Old Marguerite"]);
    const bram = web.nodes.find((n) => n.key === "bram")!;
    expect([bram.thralls, bram.boundTo]).toEqual([2, 1]);
  });

  it("draws a name only like anyone else", () => {
    const web = bondWeb({ people, bonds }, DEFAULT_FILTERS);
    expect(web.nodes.find((n) => n.key === "name:old marguerite")).toMatchObject({ character_id: null, thralls: 1 });
  });

  it("adds ended and broken bonds, not felt, and those out of play, when asked", () => {
    const web = bondWeb({ people, bonds }, { ...DEFAULT_FILTERS, who: "everyone", ended: true });
    expect(web.links).toHaveLength(5);
    const broken = web.links.find((l) => l.status === "broken")!;
    expect(broken.open).toBe(false);
    // A broken bond holds nobody.
    expect(web.nodes.find((n) => n.key === "dmitri")!.thralls).toBe(0);
  });

  it("filters to full bonds, a clan (bloodlines under their clan) or title holders", () => {
    const everyone = { ...DEFAULT_FILTERS, who: "everyone" as const };
    expect(bondWeb({ people, bonds }, { ...everyone, full: true }).links.map((l) => l.id)).toEqual(["agnes>bram"]);
    expect(bondWeb({ people, bonds }, { ...everyone, clan: "Gangrel" }).links.map((l) => l.id)).toEqual(["cora>bram"]);
    const titled = bondWeb({ people, bonds }, { ...everyone, titled: true });
    expect(titled.links.every((l) => l.thrall === "bram" || l.regnant === "bram")).toBe(true);
  });

  it("finds chains: someone bound to one regnant who holds thralls of their own", () => {
    const web = bondWeb({ people, bonds }, DEFAULT_FILTERS);
    expect(chains(web).map((c) => [c.person.name, c.regnants, c.thralls])).toEqual([["bram", ["Old Marguerite"], ["agnes", "dmitri"]]]);
  });

  it("ranks regnants by the thralls still bound to them, then full bonds", () => {
    const web = bondWeb({ people, bonds }, { ...DEFAULT_FILTERS, who: "everyone" });
    expect(mostThralls(web).map((m) => [m.person.name, m.thralls, m.full])).toEqual([
      ["bram", 3, 1],
      ["Old Marguerite", 1, 0],
    ]);
  });

  it("names clans for the filter, and how someone left play", () => {
    expect(webClans(people)).toEqual(["Gangrel", "No clan", "Toreador", "Ventrue"]);
    expect(standingText("off_field")).toBe("Off-field");
    expect(standingText("retired")).toBe("Retired");
  });
});
