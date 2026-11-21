import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { useState, type ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { TroupeProfileOut } from "../../api/types";
import { TroupeProfileView } from "./TroupeProfile";

afterEach(cleanup);

// A profile with nothing filled in yet, as a new troupe has it.
const BARE: TroupeProfileOut = {
  id: "t1",
  name: "Lords of the Night",
  abbreviation: "LotN",
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

/** The profile as the Overview shows it: `editor`, with its Edit profile. */
function Overview({ profile, leadParts }: { profile: TroupeProfileOut; leadParts?: ReactNode }) {
  const [editing, setEditing] = useState(false);
  return <TroupeProfileView profile={profile} signedIn editing={editing} onEditing={setEditing} leadParts={leadParts} />;
}

function draw(edit: boolean, profile: TroupeProfileOut = BARE, leadParts?: ReactNode) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Overview profile={{ ...profile, can_edit: edit }} leadParts={leadParts} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Draws it for an editor, with its editing parts open. */
function drawEditing() {
  draw(true);
  fireEvent.click(screen.getByRole("button", { name: "Edit profile" }));
}

const card = (title: string) => screen.getByRole("heading", { name: title }).closest("section")!;

describe("the troupe's profile on its Overview (#781, #912)", () => {
  it("shows a reader only the parts with something in them, and nothing to edit", () => {
    draw(false, { ...BARE, venue: { ...BARE.venue, name: "The Crypt" } });
    expect(screen.getByRole("heading", { name: "Where it plays" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "When it plays" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Links" })).toBeNull();
    expect(screen.queryAllByRole("button", { name: /^Edit/ })).toHaveLength(0);
  });

  it("shows its storytellers the same card as a reader, with one Edit profile in its header", () => {
    const profile = { ...BARE, venue: { ...BARE.venue, name: "The Crypt" } };
    draw(false, profile);
    const reader = screen.getByRole("region", { name: "Profile" }).textContent;
    cleanup();
    draw(true, profile);
    const region = screen.getByRole("region", { name: "Profile" });
    expect(within(region).getAllByRole("button").map((b) => b.textContent)).toEqual(["Edit profile"]);
    expect(region.textContent).toBe(`${reader!.replace("Profile", "ProfileEdit profile")}`);
    expect(screen.queryByRole("switch", { name: "Public" })).toBeNull();
  });

  it("shows what the troupe goes by, unless that is its name (#1153)", () => {
    draw(false);
    expect(screen.getByText("Abbreviation:").parentElement!.textContent).toBe("Abbreviation: LotN");
    cleanup();
    draw(false, { ...BARE, abbreviation: BARE.name });
    expect(screen.queryByText("Abbreviation:")).toBeNull();
  });

  it("shows the initials small beside the description when there is no portrait", () => {
    draw(false);
    const initials = screen.getByRole("region", { name: "Profile" }).querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(initials.textContent).toBe("LN");
    expect(initials.style.width).toBe("36px");
  });

  it("opens its editing parts on Edit profile: the switch first, then every part, empty or not, each with its own Edit", () => {
    drawEditing();
    const toggle = screen.getByRole("switch", { name: "Public" });
    expect(toggle.compareDocumentPosition(screen.getByRole("heading", { name: "Portrait and banner" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
    // Done folds them away again.
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("switch", { name: "Public" })).toBeNull();
    expect(screen.getByRole("button", { name: "Edit profile" })).toBeTruthy();
  });

  it("puts the lead's own parts after the switch, only while editing", () => {
    draw(true, BARE, <p>The lead's part</p>);
    expect(screen.queryByText("The lead's part")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit profile" }));
    const lead = screen.getByText("The lead's part");
    expect(screen.getByRole("switch", { name: "Public" }).compareDocumentPosition(lead) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("turns one part into its form, in place, until it is cancelled", () => {
    drawEditing();
    fireEvent.click(screen.getByRole("button", { name: "Edit where it plays" }));
    const where = card("Where it plays");
    expect(within(where).getByLabelText("Venue name")).toBeTruthy();
    // Only that part: the others keep their Edit.
    expect(screen.queryByLabelText("Chronicle")).toBeNull();
    expect(screen.getByRole("button", { name: "Edit the setting" })).toBeTruthy();
    fireEvent.click(within(where).getByRole("button", { name: "Cancel" }));
    expect(within(card("Where it plays")).getByText("Nothing yet.")).toBeTruthy();
  });
});
