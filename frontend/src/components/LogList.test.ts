import { describe, expect, it } from "vitest";
import { actorPlace } from "./LogList";

describe("a log line names who did it once", () => {
  it("as the sentence's first words, when it starts with them", () => {
    expect(
      actorPlace({
        actor_name: "tour-player",
        message: "tour-player finished creating Vivienne.",
      }),
    ).toEqual({
      actor: "lead",
      rest: " finished creating Vivienne.",
    });
  });

  it("not again when the sentence names them elsewhere", () => {
    expect(
      actorPlace({
        actor_name: "tour-player",
        message: "Vivienne (tour-player) joined the troupe.",
      }),
    ).toEqual({
      actor: null,
      rest: "Vivienne (tour-player) joined the troupe.",
    });
  });

  it("after a sentence that leaves them out", () => {
    expect(
      actorPlace({
        actor_name: "lead",
        message: "Vivienne's fleeting status ended.",
      }).actor,
    ).toBe("after");
  });

  it("not at all when no one did it", () => {
    expect(
      actorPlace({
        actor_name: null,
        message: "Horatio emailed jane the reset link they asked for.",
      }).actor,
    ).toBeNull();
  });

  it("only on a whole name, not one that starts another word", () => {
    expect(actorPlace({ actor_name: "Ann", message: "Anna raised Brawl." }).actor).toBe("after");
  });
});
