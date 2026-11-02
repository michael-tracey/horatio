import { describe, expect, it } from "vitest";
import { chooseTeacher, setRating, teacherOf, toChange, type CartLine } from "./cart";
import { hasTeacher, NO_TEACHER, NPC_TEACHER, teacherFields, teacherValue } from "./teachers";

const lore = { category: "skills", name: "Lore", detail: "", rating: 1 };

describe("choosing a teacher", () => {
  it("is a character of the troupe, or an NPC with a name", () => {
    expect(hasTeacher(NO_TEACHER)).toBe(false);
    expect(hasTeacher({ teacher: "Rook", teacher_id: "c1", npc: false })).toBe(true);
    expect(hasTeacher({ teacher: " ", teacher_id: null, npc: true })).toBe(false);
    expect(hasTeacher({ teacher: "Old Mother Grey", teacher_id: null, npc: true })).toBe(true);
  });

  it("shows and sends the choice", () => {
    expect(teacherValue({ teacher: "Rook", teacher_id: "c1", npc: false })).toBe("c1");
    expect(teacherValue({ teacher: "", teacher_id: null, npc: true })).toBe(NPC_TEACHER);
    expect(teacherFields({ teacher: "Rook", teacher_id: "c1", npc: false })).toEqual({ teacher: "", teacher_id: "c1" });
    expect(teacherFields({ teacher: " Old Mother Grey ", teacher_id: null, npc: true })).toEqual({ teacher: "Old Mother Grey" });
  });
});

describe("a cart line's teacher", () => {
  it("is kept on the line, sent with it, and carried to a further raise", () => {
    const [line] = setRating([], lore, 2);
    const lines = chooseTeacher([line!], line!, { teacher: "Brother Ansel", teacher_id: "c1", npc: false });
    expect(teacherOf(lines[0]!)).toEqual({ teacher: "Brother Ansel", teacher_id: "c1", npc: false });
    expect(toChange(lines[0]!)).toMatchObject({ teacher: "", teacher_id: "c1", rating: 2 });
    const raised = setRating(lines, lore, 3);
    expect(toChange(raised[0]!)).toMatchObject({ teacher_id: "c1", rating: 3 });
  });

  it("changes to an NPC, dropping the character", () => {
    const [line] = setRating([], lore, 2);
    const chosen = chooseTeacher([line!], line!, { teacher: "Rook", teacher_id: "c1", npc: false });
    const npc = chooseTeacher(chosen, chosen[0]!, { teacher: "Old Mother Grey", teacher_id: null, npc: true });
    expect(toChange(npc[0]!)).toMatchObject({ teacher: "Old Mother Grey" });
    expect(toChange(npc[0]!)).not.toHaveProperty("teacher_id");
    expect(teacherOf(npc[0]!).npc).toBe(true);
  });

  it("leaves other lines alone", () => {
    const lines: CartLine[] = [...setRating([], lore, 2), { kind: "swap", category: "focus_mentals", from_name: "Intellect", to_name: "Perception" }];
    expect(chooseTeacher(lines, lines[1]!, { teacher: "Rook", teacher_id: "c1", npc: false })[1]).toBe(lines[1]);
    expect(teacherOf(lines[1]!)).toEqual(NO_TEACHER);
  });
});
