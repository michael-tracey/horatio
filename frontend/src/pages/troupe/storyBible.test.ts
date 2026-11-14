import { describe, expect, it } from "vitest";
import type { ChronicleEvent } from "./chronicle";
import { chronology } from "./storyBible";

const event = (over: Partial<ChronicleEvent>): ChronicleEvent => ({
  key: over.key ?? "k",
  kind: "status",
  character_id: "c1",
  character_name: "Agnes",
  clan: "Ventrue",
  label: "Loyal",
  detail: "",
  at: "2026-10-03T20:00:00Z",
  on: null,
  ends_at: null,
  ends_on: null,
  ongoing: false,
  ...over,
});

describe("the story bible's chronology (#879)", () => {
  it("puts dated events in in-game order, then the rest as Horatio recorded them", () => {
    const { dated, undated } = chronology([
      event({ key: "late", on: "1990-05-01" }),
      event({ key: "joined", kind: "arrival", at: "2026-10-03T10:00:00Z" }),
      event({ key: "early", kind: "embrace", on: "1791-03-01" }),
    ]);
    expect(dated.map((e) => [e.event.key, e.when])).toEqual([
      ["early", "1 Mar 1791"],
      ["late", "1 May 1990"],
    ]);
    expect(undated.map((e) => [e.event.key, e.when])).toEqual([["joined", "3 Oct 2026"]]);
  });

  it("gives a title held still as running to now", () => {
    const { dated } = chronology([
      event({
        key: "prince",
        kind: "title",
        label: "Prince",
        on: "1950-01-01",
        ongoing: true,
      }),
    ]);
    expect(dated[0]!.when).toBe("1 Jan 1950 to now");
  });
});
