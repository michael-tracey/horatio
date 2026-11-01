import { encode } from "uqr";
import { describe, expect, it } from "vitest";
import type { Attendee } from "../../api/types";
import { checkedInText, checkInPath, checkInUrl, names, pastMonthly, qrPath, spacedCode, tidyCode, toAward } from "./checkin";

const attendee = (name: string, month_xp: number, home = true): Attendee => ({
  character_id: name,
  character_name: name,
  player: { id: name, handle: name.toLowerCase(), display_name: name },
  home,
  checked_in_at: "2026-11-01T19:00:00Z",
  by_staff: false,
  rested: true,
  month_xp,
});

describe("the door's code", () => {
  it("leads to the check-in page, which signs a signed-out person in first", () => {
    expect(checkInPath("ABC234")).toBe("/check-in/ABC234");
    expect(checkInUrl("https://horatio.example", "ABC234")).toBe("https://horatio.example/check-in/ABC234");
  });

  it("shows in two halves, and is read back however it was typed", () => {
    expect(spacedCode("ABC234")).toBe("ABC 234");
    expect(tidyCode(" abc-234 ")).toBe("ABC234");
    expect(tidyCode("abc 234")).toBe("ABC234");
  });
});

describe("the game's XP", () => {
  it("goes to those whose home is the troupe, not visitors", () => {
    expect(toAward([attendee("Agnes", 0), attendee("Vera", 0, false)]).map((a) => a.character_name)).toEqual(["Agnes"]);
  });

  it("warns of those it takes past the monthly guidance", () => {
    const here = [attendee("Agnes", 7), attendee("Bram", 5), attendee("Vera", 9, false)];
    expect(pastMonthly(here, 4, 10)).toEqual(["Agnes"]);
    expect(pastMonthly(here, 5, 10)).toEqual(["Agnes"]);
    expect(pastMonthly(here, 6, 10)).toEqual(["Agnes", "Bram"]);
    expect(pastMonthly(here, 3, 10)).toEqual([]);
  });

  it("names them in a sentence", () => {
    expect(names([])).toBe("");
    expect(names(["Agnes"])).toBe("Agnes");
    expect(names(["Agnes", "Bram"])).toBe("Agnes and Bram");
    expect(names(["Agnes", "Bram", "Cleo"])).toBe("Agnes, Bram and Cleo");
  });

  it("says how many came", () => {
    expect(checkedInText(0)).toBe("Nobody checked in yet");
    expect(checkedInText(3)).toBe("3 checked in");
  });
});

describe("the QR code", () => {
  it("draws a square for each dark module", () => {
    expect(
      qrPath([
        [true, false],
        [false, true],
      ]),
    ).toBe("M0 0h1v1h-1zM1 1h1v1h-1z");
  });

  it("holds the link, with its finder squares inside the quiet border", () => {
    const qr = encode(checkInUrl("https://horatio.example", "ABC234"), { ecc: "M", border: 4 });
    // The top-left finder: a 7×7 dark ring, after the 4-module border.
    const ring = [0, 6].flatMap((i) => [0, 1, 2, 3, 4, 5, 6].flatMap((j) => [qr.data[4 + i]![4 + j], qr.data[4 + j]![4 + i]]));
    expect(ring.every(Boolean)).toBe(true);
    expect(qr.data[3]![3]).toBe(false);
    expect(qr.size).toBe(qr.data.length);
  });
});
