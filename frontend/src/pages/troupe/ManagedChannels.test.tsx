import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ManagedCharacterRow, ManagedChannels } from "./ManagedChannels";

afterEach(cleanup);

function wrap(children: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>);
}

const off = { on: false, staff_roles: [], roles: [], lacks: [], can_invite: true, queued: 0, characters: {} };

describe("channels Horatio makes (#855)", () => {
  it("asks only to be switched on while off", () => {
    wrap(<ManagedChannels troupeId="t1" managed={off} canEdit without={2} />);
    expect((screen.getByRole("checkbox", { name: "Let Horatio make each character's private channel" }) as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByText("Staff roles let into every channel")).toBeNull();
    expect(screen.queryByRole("button", { name: "Make channels for every character without one" })).toBeNull();
  });

  it("says what the bot lacks, picks staff roles and shows what's being made", () => {
    wrap(
      <ManagedChannels
        troupeId="t1"
        managed={{
          ...off,
          on: true,
          staff_roles: ["800"],
          roles: [
            { id: "800", name: "sts" },
            { id: "801", name: "players" },
          ],
          lacks: ["Manage Channels", "Manage Roles"],
          can_invite: false,
          queued: 3,
        }}
        canEdit
        without={3}
      />,
    );
    expect(screen.getAllByRole("status")[0]!.textContent).toBe(
      "To make channels, the Horatio bot needs Manage Channels and Manage Roles on the server. Give them to its role in Discord's Server Settings › Roles.",
    );
    expect((screen.getByRole("checkbox", { name: "@sts" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "@players" }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/can't invite players who aren't on the server/)).toBeTruthy();
    expect(screen.getByText(/Making 3 channels/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Make channels for every character without one" })).toBeTruthy();
  });

  it("asks a storyteller whether the member a typed username found is the player", () => {
    wrap(
      <ManagedCharacterRow
        troupeId="t1"
        characterId="c1"
        name="Agnes Wren"
        state={{
          status: "confirm",
          note: "…",
          made: false,
          discord: "typed",
          username: "nightowl",
          match: { username: "nightowl", display_name: "Owl", avatar: null },
        }}
        hasChannel={false}
        canEdit
        onMade={() => undefined}
      />,
    );
    const group = screen.getByRole("group", { name: "Confirm Agnes Wren's player on Discord" });
    expect(group.textContent).toContain("Is @nightowl (Owl) Agnes Wren's player?");
    expect(screen.getByRole("button", { name: "Yes, let them in" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Make a channel for Agnes Wren" })).toBeNull();
  });

  it("offers to make a channel, and says what stood in the way last time", () => {
    wrap(
      <ManagedCharacterRow
        troupeId="t1"
        characterId="c1"
        name="Agnes Wren"
        state={{ status: "not_found", note: "No one on the server has the Discord username @ghost.", made: false, discord: "typed", username: "ghost", match: null }}
        hasChannel={false}
        canEdit
        onMade={() => undefined}
      />,
    );
    expect(screen.getByText("Discord: @ghost, typed, not checked")).toBeTruthy();
    expect(screen.getByText("No one on the server has the Discord username @ghost.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Make a channel for Agnes Wren" })).toBeTruthy();
  });
});
