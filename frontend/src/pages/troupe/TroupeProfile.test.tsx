import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { TroupeProfileOut } from "../../api/types";
import { TroupeProfileView } from "./TroupeProfile";

afterEach(cleanup);

// A profile with nothing filled in yet, as a new troupe has it.
const BARE: TroupeProfileOut = {
  id: "t1",
  name: "Lords of the Night",
  description: "",
  public: false,
  portrait: null,
  portrait_crop: null,
  banner: null,
  links: { website: null, discord: null, facebook: null, instagram: null, join: null },
  schedule: "",
  games: [],
  venue: { region: "", name: "", address: "", address_hidden: false, access: "" },
  setting: { chronicle: "", city: "", era: "" },
  new_players: null,
  contact: null,
  lead: { id: "u1", handle: "night_owl", display_name: "Mara" },
  min_age: null,
  content_notes: "",
  written_rules: [],
  can_edit: true,
  pictures_available: true,
  setting_document: false,
};

function draw(edit: boolean, profile: TroupeProfileOut = BARE) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <TroupeProfileView profile={profile} signedIn edit={edit} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const card = (title: string) => screen.getByRole("heading", { name: title }).closest("section")!;

describe("the troupe's profile on its Overview (#781)", () => {
  it("shows a reader only the parts with something in them, and nothing to edit", () => {
    draw(false, { ...BARE, venue: { ...BARE.venue, name: "The Crypt" } });
    expect(screen.getByRole("heading", { name: "Where it plays" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "When it plays" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Links" })).toBeNull();
    expect(screen.queryAllByRole("button", { name: /^Edit / })).toHaveLength(0);
  });

  it("gives its storytellers every part, empty or not, each with its own Edit", () => {
    draw(true);
    for (const title of ["Links", "When it plays", "Where it plays", "The setting", "New players", "Age and content"]) {
      expect(within(card(title)).getByText("Nothing yet.")).toBeTruthy();
    }
    expect(screen.getAllByRole("button", { name: /^Edit / }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Edit links",
      "Edit when it plays",
      "Edit where it plays",
      "Edit the setting",
      "Edit new players",
      "Edit age and content",
    ]);
    expect(screen.getByRole("heading", { name: "Portrait and banner" })).toBeTruthy();
  });

  it("turns one card into its form, in place, until it is cancelled", () => {
    draw(true);
    fireEvent.click(screen.getByRole("button", { name: "Edit where it plays" }));
    const where = card("Where it plays");
    expect(within(where).getByLabelText("Venue name")).toBeTruthy();
    // Only that card: the others keep their Edit.
    expect(screen.queryByLabelText("Chronicle")).toBeNull();
    expect(screen.getByRole("button", { name: "Edit the setting" })).toBeTruthy();
    fireEvent.click(within(where).getByRole("button", { name: "Cancel" }));
    expect(within(card("Where it plays")).getByText("Nothing yet.")).toBeTruthy();
  });
});
