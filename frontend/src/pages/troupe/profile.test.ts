import { describe, expect, it } from "vitest";
import type { TroupeProfileOut } from "../../api/types";
import { editable, hasProfile, linksOf, newPlayersText } from "./profile";

const bare: TroupeProfileOut = {
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
  setting: { chronicle: "", city: "", era: "", tone: "" },
  new_players: null,
  contact: null,
  lead: { id: "u1", handle: "night_owl", display_name: "Mara" },
  min_age: null,
  content_notes: "",
  can_edit: false,
  pictures_available: true,
};

describe("troupe profiles", () => {
  it("lists only the links it has, in their order", () => {
    const links = linksOf({ ...bare.links, join: "https://x.org/join", website: "https://x.org" });
    expect(links.map((l) => [l.kind, l.label])).toEqual([
      ["website", "Website"],
      ["join", "How to join"],
    ]);
  });

  it("says whether new players are welcome", () => {
    expect(newPlayersText("welcoming")).toBe("Welcoming new players");
    expect(newPlayersText("closed")).toBe("Not taking new players right now");
    expect(newPlayersText(null)).toBeNull();
  });

  it("knows a profile with nothing in it", () => {
    expect(hasProfile(bare)).toBe(false);
    expect(hasProfile({ ...bare, min_age: 18 })).toBe(true);
    expect(hasProfile({ ...bare, min_age: 0 })).toBe(true);
    // An address hidden from someone signed out is still something there.
    expect(hasProfile({ ...bare, venue: { ...bare.venue, address: null, address_hidden: true } })).toBe(true);
  });

  it("starts the editor from what is saved", () => {
    const form = editable({ ...bare, public: true, contact: bare.lead, links: { ...bare.links, discord: "https://discord.gg/x" } });
    // The switch saves that on its own, so the editor leaves it as it is.
    expect(form.public).toBeUndefined();
    expect(form.contact_id).toBe("u1");
    expect(form.links).toEqual({ website: "", discord: "https://discord.gg/x", facebook: "", instagram: "", join: "" });
  });
});
