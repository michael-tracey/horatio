import { describe, expect, it } from "vitest";
import type { TroupeOut } from "../api/types";
import { excerpt, matches, ownFirst } from "./troupeList";

const troupe = (name: string, mine: Partial<TroupeOut> = {}) =>
  ({ name, place: "", description: "", my_role: null, my_characters: [], ...mine }) as TroupeOut;

describe("excerpt", () => {
  it("keeps a short description as it is", () => {
    expect(excerpt("  A Camarilla game in Leeds.  ")).toBe("A Camarilla game in Leeds.");
  });

  it("takes the first paragraph as one line, without Markdown's marks", () => {
    expect(excerpt("## The **Court** of\n_Leeds_, see [our site](https://example.com)\n\nMore later.")).toBe("The Court of Leeds, see our site");
  });

  it("cuts a long one at a word", () => {
    const long = "word ".repeat(60);
    const cut = excerpt(long);
    expect(cut.endsWith("word…")).toBe(true);
    expect(cut.length).toBeLessThanOrEqual(161);
  });

  it("says nothing for no description", () => {
    expect(excerpt("")).toBe("");
  });
});

describe("ownFirst", () => {
  it("puts the troupes played in or run first, each part by name", () => {
    const list = [troupe("Barons"), troupe("Court", { my_characters: ["Agnes"] }), troupe("Abbey"), troupe("Dukes", { my_role: "narrator" })];
    expect(ownFirst(list).map((t) => t.name)).toEqual(["Court", "Dukes", "Abbey", "Barons"]);
  });
});

describe("matches", () => {
  it("finds every word in the name, place or description", () => {
    const t = troupe("Lords of the Night", { place: "Leeds", description: "A Sabbat chronicle." });
    expect(matches(t, "lords leeds")).toBe(true);
    expect(matches(t, "SABBAT")).toBe(true);
    expect(matches(t, "  ")).toBe(true);
    expect(matches(t, "york")).toBe(false);
  });
});
