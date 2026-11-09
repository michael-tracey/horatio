import { describe, expect, it } from "vitest";
import type { CharacterListOut } from "../api/types";
import { datesFor } from "../dates";
import { standing, waiting } from "./characterList";

const character = (c: Partial<CharacterListOut> = {}) =>
  ({
    status: "active",
    creation_complete: true,
    home_troupe_id: null,
    home_troupe_name: null,
    asking_troupe_id: null,
    asking_troupe_name: null,
    building_troupe_id: null,
    building_troupe_name: null,
    downtime_due: null,
    delivered: [],
    ...c,
  }) as CharacterListOut;

const labels = (notes: { label: string }[]) => notes.map((n) => n.label);
const dates = datesFor({ time_zone: "America/New_York", date_format: "day_month", clock: "12" });
const now = new Date("2026-11-02T12:00:00Z");

describe("standing", () => {
  it("says a character still being made is in creation, and whose rules it is built to", () => {
    expect(standing(character({ creation_complete: false, building_troupe_id: "a", building_troupe_name: "Ashes" }))).toEqual([
      { label: "In creation", tone: "gold" },
      { label: "Built to Ashes's rules", tone: "mist" },
    ]);
    expect(labels(standing(character({ creation_complete: false })))).toEqual(["In creation", "Built to the book's rules"]);
  });

  it("names the troupe it waits for, and its home", () => {
    // Asking the troupe it is built for: "Waiting for" says whose rules.
    expect(labels(standing(character({ asking_troupe_id: "a", asking_troupe_name: "Ashes", building_troupe_id: "a", building_troupe_name: "Ashes" })))).toEqual([
      "Waiting for Ashes",
    ]);
    expect(labels(standing(character({ home_troupe_id: "a", home_troupe_name: "Ashes" })))).toEqual(["Home: Ashes"]);
    // Moving: still at home in one while the other decides.
    expect(labels(standing(character({ home_troupe_id: "a", home_troupe_name: "Ashes", asking_troupe_id: "e", asking_troupe_name: "Embers" })))).toEqual([
      "Home: Ashes",
      "Waiting for Embers",
    ]);
  });

  it("asks for a home troupe once the character is finished, saying whose rules it is built to", () => {
    expect(standing(character())).toEqual([
      { label: "No home troupe yet", tone: "gold" },
      { label: "Built to the book's rules", tone: "mist" },
    ]);
    expect(labels(standing(character({ building_troupe_id: "a", building_troupe_name: "Ashes" })))).toEqual(["No home troupe yet", "Built to Ashes's rules"]);
  });

  it("says retired, whatever else is true", () => {
    expect(labels(standing(character({ status: "retired", home_troupe_name: "Ashes" })))).toEqual(["Retired"]);
  });
});

describe("waiting", () => {
  it("gives the day and time a downtime is due, or says it is overdue", () => {
    expect(labels(waiting(character({ downtime_due: "2026-11-08T04:59:00Z" }), null, dates, now))).toEqual(["Downtime due Sat 7 Nov, 11:59 pm"]);
    expect(labels(waiting(character({ downtime_due: "2026-11-01T04:59:00Z" }), null, dates, now))).toEqual(["Downtime overdue"]);
  });

  it("counts results new until they are seen on this device", () => {
    const delivered = ["2026-11-01T10:00:00Z"];
    expect(labels(waiting(character({ delivered }), null, dates, now))).toEqual(["New results"]);
    expect(labels(waiting(character({ delivered }), "2026-11-01T10:00:00Z", dates, now))).toEqual([]);
  });

  it("says nothing for a retired character or one still being made", () => {
    const due = { downtime_due: "2026-11-08T04:59:00Z", delivered: ["2026-11-01T10:00:00Z"] };
    expect(waiting(character({ ...due, status: "retired" }), null, dates, now)).toEqual([]);
    expect(waiting(character({ ...due, creation_complete: false }), null, dates, now)).toEqual([]);
  });
});
