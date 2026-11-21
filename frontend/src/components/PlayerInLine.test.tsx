import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { PlayerInLine } from "./PlayerInLine";

afterEach(cleanup);

const shown = (props: Parameters<typeof PlayerInLine>[0]) =>
  render(
    <MemoryRouter>
      <p>
        <PlayerInLine {...props} />
      </p>
    </MemoryRouter>,
  ).container.textContent;

describe("a line naming a player", () => {
  it("links the name in parentheses to their profile, the rest as it is (#1131)", () => {
    expect(shown({ text: "Teaching Firearms 1 to Konrad (Nick)", playerId: "u2", playerName: "Nick" })).toBe("Teaching Firearms 1 to Konrad (Nick)");
    expect(screen.getByRole("link", { name: "Nick" }).getAttribute("href")).toBe("/players/u2");
  });

  it("is the line alone without a player, or when it doesn't name them so", () => {
    expect(shown({ text: "Teaching Firearms 1 to Sergeant Hale", playerId: null, playerName: null })).toBe("Teaching Firearms 1 to Sergeant Hale");
    expect(shown({ text: "Teaching Firearms 1 to Nick", playerId: "u2", playerName: "Nick" })).toBe("Teaching Firearms 1 to Nick");
    expect(screen.queryByRole("link")).toBeNull();
  });
});
