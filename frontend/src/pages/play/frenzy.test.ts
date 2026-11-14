import { describe, expect, it } from "vitest";
import { frenzyNumbers } from "./frenzy";

const mental = (value: number) => ({ label: "Mental", value });

describe("resisting frenzy with the player's numbers", () => {
  it("is Mental + Willpower now against 10 + Beast traits", () => {
    expect(frenzyNumbers({ parts: [mental(3)], beast: [], switched_beast: [] }, 6, 2, { name: "Humanity", value: 5 })).toEqual({
      pool: 9,
      against: 12,
      poolParts: "Mental 3 + Willpower 6",
      againstParts: "10 + Beast traits 2",
    });
  });

  it("adds 5 at Humanity 2 or less, but not on a path", () => {
    expect(frenzyNumbers({ parts: [mental(3)], beast: [], switched_beast: [] }, 4, 1, { name: "Humanity", value: 2 }).against).toBe(16);
    expect(frenzyNumbers({ parts: [mental(3)], beast: [], switched_beast: [] }, 4, 1, { name: "Path of Night", value: 2 }).against).toBe(11);
  });

  it("counts what merits and flaws add, and the Beast traits they count, never below none", () => {
    const calm = { parts: [mental(4), { label: "Calm Heart", value: 3 }], beast: [{ label: "Calm Heart", value: -2 }], switched_beast: [] };
    const you = frenzyNumbers(calm, 5, 1, null);
    expect([you.pool, you.against]).toEqual([12, 10]);
    expect(you.poolParts).toBe("Mental 4 + Calm Heart 3 + Willpower 5");
    expect(you.againstParts).toBe("10 + Beast traits 1 − Calm Heart 2");
    expect(frenzyNumbers({ parts: [mental(4)], beast: [{ label: "Short Fuse", value: 1 }], switched_beast: [] }, 5, 3, null).against).toBe(14);
  });
});

describe("Beast traits that count while a power is on (#822)", () => {
  const heart = { switch: "Heart removed", label: "Heart of Darkness", value: -1 };

  it("counts Heart of Darkness's one fewer only while the heart is out", () => {
    const resist = { parts: [mental(3)], beast: [], switched_beast: [heart] };
    expect(frenzyNumbers(resist, 5, 2, null).against).toBe(12);
    const out = frenzyNumbers(resist, 5, 2, null, ["Heart removed"]);
    expect(out.against).toBe(11);
    expect(out.againstParts).toBe("10 + Beast traits 2 − Heart of Darkness 1");
  });

  it("reads a view kept on the phone from before, without them", () => {
    expect(frenzyNumbers({ parts: [mental(3)], beast: [] } as never, 5, 2, null, ["Heart removed"]).against).toBe(12);
  });
});
