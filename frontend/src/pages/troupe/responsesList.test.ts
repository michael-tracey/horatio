import { describe, expect, it } from "vitest";
import { assigneeOf, byCharacter, questionsOf, responsesCount, shows } from "./responsesList";

const item = (id: string, character: string, over: Partial<Parameters<typeof assigneeOf>[0]> = {}) => ({
  id,
  character_id: character.toLowerCase(),
  character_name: character,
  question: "Downtime action",
  status: "unassigned",
  assigned_to_user_id: null,
  assigned_to_any_narrator: false,
  ...over,
});

describe("responses list", () => {
  it("says who a response is with", () => {
    expect(assigneeOf(item("1", "Agnes"))).toBe("none");
    expect(assigneeOf(item("1", "Agnes", { assigned_to_any_narrator: true }))).toBe("any");
    expect(assigneeOf(item("1", "Agnes", { assigned_to_user_id: "u1", status: "assigned" }))).toBe("u1");
  });

  it("filters by status, assignee and question together", () => {
    const elite = item("1", "Agnes", { question: "Elite influence action", assigned_to_user_id: "u1", status: "assigned" });
    const any = { status: "all" as const, assignee: "", question: "" };
    expect(shows(elite, any)).toBe(true);
    expect(shows(elite, { ...any, status: "unassigned" })).toBe(false);
    expect(shows(elite, { ...any, assignee: "u1" })).toBe(true);
    expect(shows(elite, { ...any, assignee: "none" })).toBe(false);
    expect(shows(elite, { ...any, question: "Elite influence action" })).toBe(true);
    expect(shows(elite, { ...any, question: "Downtime action" })).toBe(false);
  });

  it("groups by character in the order given, and lists each question once", () => {
    const items = [item("1", "Agnes"), item("2", "Agnes", { question: "Nominations?" }), item("3", "Bram")];
    expect(byCharacter(items).map((g) => [g.name, g.items.map((i) => i.id)])).toEqual([
      ["Agnes", ["1", "2"]],
      ["Bram", ["3"]],
    ]);
    expect(questionsOf(items)).toEqual(["Downtime action", "Nominations?"]);
  });

  it("counts responses", () => {
    expect(responsesCount(1)).toBe("1 response");
    expect(responsesCount(3)).toBe("3 responses");
  });
});
