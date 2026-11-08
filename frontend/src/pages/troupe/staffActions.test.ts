import { describe, expect, it } from "vitest";
import { staffActions, type ActionTarget, type Staffing } from "./staffActions";

const pc: ActionTarget = { kind: "pc", home: true, retired: false, givable: false, npc_form: null, picture: null, social_age: "Neonate" };
const npc: ActionTarget = { kind: "npc", home: false, retired: false, givable: true, npc_form: "sheeted", picture: null, social_age: "Elder" };
const storyteller: Staffing = { running: true, storyteller: true, archived: false };
const assistant: Staffing = { ...storyteller, storyteller: false };

describe("staffActions", () => {
  it("offers a home PC everything but giving, most used first, then the printouts", () => {
    expect(staffActions(pc, storyteller)).toEqual({ doing: ["xp", "equipment", "status", "titles"], printing: ["sheet", "badge"] });
  });

  it("gives a visitor only its titles here and the printouts: its home troupe keeps the rest", () => {
    expect(staffActions({ ...pc, home: false }, storyteller)).toEqual({ doing: ["titles"], printing: ["sheet", "badge"] });
  });

  it("offers an NPC its Play View and its Who's Who listing, no XP, and giving it to a player only to storytellers, and only one that can be given", () => {
    expect(staffActions(npc, storyteller).doing).toEqual(["play", "equipment", "status", "titles", "listing", "give", "claim"]);
    expect(staffActions(npc, assistant).doing).toEqual(["play", "equipment", "status", "titles", "listing"]);
    expect(staffActions({ ...npc, givable: false }, storyteller).doing).toEqual(["play", "equipment", "status", "titles", "listing"]);
  });

  it("prints no sheet for a Stock NPC, which has none: only its badge", () => {
    expect(staffActions(npc, storyteller).printing).toEqual(["sheet", "badge"]);
    expect(staffActions({ ...npc, npc_form: "stock", givable: false }, storyteller).printing).toEqual(["badge"]);
  });

  it("gives a retired character no equipment", () => {
    expect(staffActions({ ...pc, retired: true }, storyteller).doing).toEqual(["xp", "status", "titles"]);
  });

  it("in an archived troupe, open only to the custodian, gives no NPC away", () => {
    expect(staffActions(npc, { ...storyteller, archived: true }).doing).toEqual(["play", "equipment", "status", "titles", "listing"]);
  });

  it("shows the Jyhad card of a vampire with a picture, after the printouts (#537)", () => {
    expect(staffActions({ ...pc, picture: "/p" }, storyteller).printing).toEqual(["sheet", "badge", "jyhad"]);
    expect(staffActions({ ...npc, picture: "/p", social_age: "Ghoul" }, storyteller).printing).toEqual(["sheet", "badge"]);
  });

  it("offers nothing to anyone who doesn't run the troupe", () => {
    expect(staffActions(pc, { running: false, storyteller: false, archived: false })).toEqual({ doing: [], printing: [] });
  });
});
