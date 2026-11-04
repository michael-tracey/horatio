import { describe, expect, it } from "vitest";
import { buildManual, buildPage, inOrder, resolveLink, search, sections, snippet } from "./manual";
import { manualLink } from "../manualLink";

describe("manualLink", () => {
  it("is where a part of the manual is in the app", () => {
    expect(manualLink()).toBe("/help");
    expect(manualLink("players")).toBe("/help/players");
    expect(manualLink("players", "downtimes")).toBe("/help/players#downtimes");
  });
});

describe("resolveLink", () => {
  it("turns links between pages into the app's", () => {
    expect(resolveLink("glossary", "players.md#downtimes")).toEqual({ kind: "page", page: "players", anchor: "downtimes", to: "/help/players#downtimes" });
    expect(resolveLink("glossary", "./players.md")).toEqual({ kind: "page", page: "players", anchor: null, to: "/help/players" });
    expect(resolveLink("players", "README.md")).toEqual({ kind: "page", page: "README", anchor: null, to: "/help" });
    expect(resolveLink("players", "#spending-xp")).toEqual({ kind: "page", page: "players", anchor: "spending-xp", to: "/help/players#spending-xp" });
    expect(resolveLink("README", "#contents")).toMatchObject({ to: "/help#contents" });
  });

  it("keeps web links and leaves anything else for the link test", () => {
    expect(resolveLink("players", "https://github.com/michael-tracey/horatio")).toEqual({
      kind: "external",
      href: "https://github.com/michael-tracey/horatio",
    });
    expect(resolveLink("players", "images/players/sheet.png")).toEqual({ kind: "other", href: "images/players/sheet.png" });
    expect(resolveLink("players", "../CONTEXT.md")).toEqual({ kind: "other", href: "../CONTEXT.md" });
  });
});

describe("buildPage", () => {
  it("gives headings their anchors, in quotes too", () => {
    const page = buildPage("players", "# Players\n\n## Spending XP & approvals\n\n> ## Quoted\n\n## Spending XP & approvals");
    expect(page.title).toBe("Players");
    expect(page.headings.map((h) => h.id)).toEqual(["players", "spending-xp--approvals", "quoted", "spending-xp--approvals-1"]);
  });
});

const manual = buildManual({
  "README.md": "# Manual\n\n- [Players](players.md)\n- **[Glossary](glossary.md)**",
  "players.md":
    "# Players\n\nFor players.\n\n## Downtimes\n\nWrite your **downtime** before the due date. Feeding comes first.\n\n### Feeding\n\n| Kind | When |\n| --- | --- |\n| Hunt | Each cycle |",
  "glossary.md": "# Glossary\n\n## Downtime cycle\n\nOne round of downtimes.",
  "custodian.md": "# Custodian\n\nThe site's keeper.",
});

describe("sections", () => {
  it("cuts a page at its headings, with the words under each", () => {
    expect(sections(manual.pages.get("players")!)).toEqual([
      { page: "players", pageTitle: "Players", heading: null, anchor: null, text: "For players." },
      {
        page: "players",
        pageTitle: "Players",
        heading: "Downtimes",
        anchor: "downtimes",
        text: "Write your downtime before the due date. Feeding comes first.",
      },
      { page: "players", pageTitle: "Players", heading: "Feeding", anchor: "feeding", text: "Kind When Hunt Each cycle" },
    ]);
  });
});

describe("inOrder", () => {
  it("puts pages in the contents' order, then the rest, then the contents", () => {
    expect(inOrder(manual).map((p) => p.name)).toEqual(["players", "glossary", "custodian", "README"]);
  });
});

describe("search", () => {
  it("finds every section with all the words, a heading first, linking to its anchor", () => {
    const hits = search(manual, "downtime");
    expect(hits.map((h) => h.to)).toEqual(["/help/players#downtimes", "/help/glossary#downtime-cycle"]);
    expect(hits[0]!.section.heading).toBe("Downtimes");
  });

  it("needs every word, in any case", () => {
    expect(search(manual, "FEEDING cycle").map((h) => h.to)).toEqual(["/help/players#feeding"]);
    expect(search(manual, "feeding nothing")).toEqual([]);
    expect(search(manual, "   ")).toEqual([]);
  });

  it("finds words under a page's title, linking to the page", () => {
    expect(search(manual, "keeper").map((h) => h.to)).toEqual(["/help/custodian"]);
  });
});

describe("snippet", () => {
  it("shows the words around the first match, marked", () => {
    expect(snippet("Write your downtime before the due date.", ["due"])).toEqual([
      { text: "Write your downtime before the ", match: false },
      { text: "due", match: true },
      { text: " date.", match: false },
    ]);
  });

  it("cuts long text at words, with an ellipsis", () => {
    const text = `${"word ".repeat(40)}target ${"more ".repeat(60)}`.trim();
    const parts = snippet(text, ["target"]);
    const shown = parts.map((p) => p.text).join("");
    expect(shown.startsWith("…word")).toBe(true);
    expect(shown.endsWith("more…")).toBe(true);
    expect(parts.filter((p) => p.match).map((p) => p.text)).toEqual(["target"]);
  });
});
