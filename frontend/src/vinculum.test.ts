import { describe, expect, it } from "vitest";
import type { TroupeVinculumOut, VaulderieOut } from "./api/types";
import { matrix, participantsText, ratingName, vaulderieState } from "./vinculum";

const who = (name: string, id: string | null = null) => ({ character_id: id, name, kind: id ? ("pc" as const) : null });

describe("the Vinculum", () => {
  it("names each rating, keeping to 1 to 5", () => {
    expect(ratingName(1)).toBe("Kinship");
    expect(ratingName(5)).toBe("Infatuation");
    expect(ratingName(9)).toBe("Infatuation");
  });

  it("lists who took part, marking a false Sabbat", () => {
    const v = {
      participants: [
        { who: who("Agnes", "a"), false_sabbat: false },
        { who: who("Bram", "b"), false_sabbat: false },
        { who: who("Ezra"), false_sabbat: true },
      ],
    } as Pick<VaulderieOut, "participants">;
    expect(participantsText(v)).toBe("Agnes, Bram and Ezra (false Sabbat)");
  });

  it("says where a Vaulderie stands", () => {
    expect(vaulderieState({ status: "pending", reason: "" })).toBe("Waiting for the storytellers");
    expect(vaulderieState({ status: "declined", reason: "Not there" })).toBe("Declined: Not there");
    expect(vaulderieState({ status: "recorded", reason: "" })).toBe("Counts");
  });

  it("narrows the matrix to one Vaulderie's circle, as a pack", () => {
    const data = {
      people: [
        { key: "a", who: who("Agnes", "a") },
        { key: "b", who: who("Bram", "b") },
        { key: "name:ezra", who: who("Ezra") },
      ],
      ratings: [
        { felt_by: "a", toward: "b", rating: 2 },
        { felt_by: "b", toward: "a", rating: 2 },
      ],
      vaulderies: [
        {
          id: "v1",
          participants: [
            { who: who("Agnes", "a"), false_sabbat: false },
            { who: who("Ezra"), false_sabbat: false },
          ],
        },
      ],
    } as unknown as TroupeVinculumOut;
    const all = matrix(data, null);
    expect(all.people.map((p) => p.who.name)).toEqual(["Agnes", "Bram", "Ezra"]);
    expect(all.rating("a", "b")).toBe(2);
    expect(all.rating("a", "name:ezra")).toBe(0);
    expect(matrix(data, "v1").people.map((p) => p.who.name)).toEqual(["Agnes", "Ezra"]);
  });
});
