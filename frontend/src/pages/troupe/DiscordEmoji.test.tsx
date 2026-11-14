import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { EmojiChoice } from "./DiscordEmoji";

afterEach(cleanup);

type Emoji = components["schemas"]["EmojiOut"];

function wrap(children: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      {children}
    </QueryClientProvider>,
  );
}

const symbol = (
  key: string,
  group: Emoji["symbols"][number]["group"],
  label: string,
  name: string,
  added: "server" | "own" | null = null,
) => ({
  key,
  group,
  label,
  name,
  added,
  other_style: false,
  status: added ? "added" : null,
  note: added ? `Added as :${name}:.` : null,
});

const off: Emoji = {
  on: false,
  style: "png_wb",
  own: false,
  fetched: true,
  lacks: [],
  room: { boost: 0, room: 50, used: 49 },
  symbols: [
    symbol("clan/brujah", "clan", "Brujah", "brujah", "server"),
    symbol("clan/tremere", "clan", "Tremere", "tremere"),
    symbol("disc/sup/aus", "disc/sup", "Auspex (superior)", "aus_sup"),
    symbol("path/caine", "path", "Caine", "path_caine"),
  ],
  clans: ["clan/tremere"],
  disciplines: ["disc/sup/aus"],
  queued: 0,
};

describe("clan and discipline emoji (#870)", () => {
  it("asks only to be switched on while off", () => {
    wrap(<EmojiChoice troupeId="t1" emoji={off} canEdit />);
    expect(
      (
        screen.getByRole("checkbox", {
          name: "Let Horatio add the clan and discipline symbols to the server as emoji",
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);
    expect(
      screen.queryByRole("button", { name: "Add the chosen emoji" }),
    ).toBeNull();
  });

  it("shows the room, starts from what's added, and warns what won't fit", () => {
    wrap(
      <EmojiChoice
        troupeId="t1"
        emoji={{ ...off, on: true, lacks: ["Create Expressions"] }}
        canEdit
      />,
    );
    expect(
      screen.getByText(/needs Create Expressions on the server/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "The server has 1 of 50 emoji slots free (Server Boost level 0).",
      ),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("checkbox", {
          name: "Brujah (:brujah:)",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(
      (
        screen.getByRole("checkbox", {
          name: "Tremere (:tremere:)",
        }) as HTMLInputElement
      ).checked,
    ).toBe(false);

    fireEvent.click(
      screen.getByRole("button", { name: "This troupe's clans" }),
    );
    expect(
      (
        screen.getByRole("checkbox", {
          name: "Tremere (:tremere:)",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    // One to add, one slot: it fits.
    expect(screen.queryByText(/won't fit/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Everything" }));
    expect(
      screen.getByText(/2 of the 3 to add won't fit/).textContent,
    ).toContain("and lists the rest");
  });

  it("says when the symbols aren't fetched", () => {
    wrap(
      <EmojiChoice
        troupeId="t1"
        emoji={{ ...off, fetched: false, symbols: [] }}
        canEdit
      />,
    );
    expect(
      screen.getByText(/hasn't fetched the VTES symbols in this style yet/),
    ).toBeTruthy();
  });
});
