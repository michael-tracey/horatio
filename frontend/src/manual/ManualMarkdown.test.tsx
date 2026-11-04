import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { Markdown } from "../components/Markdown";
import { parseBlocks, parseManual } from "../markdown";
import { buildPage } from "./manual";
import { ManualMarkdown } from "./ManualMarkdown";

afterEach(cleanup);

function show(text: string, { images = {}, highlight }: { images?: Record<string, string>; highlight?: string } = {}) {
  const page = buildPage("players", text);
  return render(
    <MemoryRouter>
      <ManualMarkdown page="players" blocks={page.blocks} images={images} highlight={highlight} />
    </MemoryRouter>,
  ).container;
}

describe("parseManual", () => {
  it("reads pipe tables, with their alignment and escaped pipes", () => {
    const [table] = parseManual("| Role | Can | Count |\n| :--- | :-: | --: |\n| Narrator | answer `a \\| b` | 2 |\n| Storyteller | everything");
    expect(table).toMatchObject({ t: "table", align: ["left", "center", "right"] });
    if (table?.t !== "table") throw new Error("not a table");
    expect(table.head.map((c) => c[0])).toEqual([
      { t: "text", v: "Role" },
      { t: "text", v: "Can" },
      { t: "text", v: "Count" },
    ]);
    expect(table.rows).toHaveLength(2);
    expect(table.rows[0]![1]).toEqual([
      { t: "text", v: "answer " },
      { t: "code", v: "a \\| b" },
    ]);
    // A short row is filled out to the header's width.
    expect(table.rows[1]![2]).toEqual([]);
  });

  it("reads images and relative links", () => {
    expect(parseManual("![The sheet](images/players/sheet.png) and [XP](players.md#spending-xp)")).toEqual([
      {
        t: "p",
        c: [
          { t: "image", src: "images/players/sheet.png", alt: "The sheet" },
          { t: "text", v: " and " },
          { t: "link", href: "players.md#spending-xp", c: [{ t: "text", v: "XP" }] },
        ],
      },
    ]);
  });

  it("nests lists under an item, as GitHub does", () => {
    const [list] = parseManual(
      "1. Open it.\n2. Fill in:\n   - **Name**: yours.\n     Still the name.\n   - Handle.\n\n     A second paragraph.\n3. Done.\n- Not part of it",
    );
    expect(list).toMatchObject({ t: "ol", start: 1 });
    if (list?.t !== "ol") throw new Error("not a list");
    expect(list.items).toHaveLength(3);
    expect(list.children?.[0]).toBeUndefined();
    const inner = list.children?.[1];
    expect(inner?.map((b) => b.t)).toEqual(["ul"]);
    if (inner?.[0]?.t !== "ul") throw new Error("not a list");
    expect(inner[0].items).toHaveLength(2);
    expect(inner[0].items[0]).toEqual([
      { t: "strong", c: [{ t: "text", v: "Name" }] },
      { t: "text", v: ": yours." },
      { t: "br" },
      { t: "text", v: "Still the name." },
    ]);
    expect(inner[0].children?.[1]?.map((b) => b.t)).toEqual(["p"]);
  });

  it("keeps a two-space bullet under a bullet as its child", () => {
    const [list] = parseManual("- one\n  - one a\n- two");
    if (list?.t !== "ul") throw new Error("not a list");
    expect(list.items).toHaveLength(2);
    expect(list.children?.[0]?.[0]).toMatchObject({ t: "ul", items: [[{ t: "text", v: "one a" }]] });
  });

  it("never takes a link or image with a scheme other than the web's", () => {
    for (const href of ["javascript:alert(1)", "data:text/html,x", "//evil.example/x", "vbscript:x"]) {
      expect(parseManual(`[x](${href}) ![y](${href})`)[0]).toEqual({ t: "p", c: [{ t: "text", v: `[x](${href}) ![y](${href})` }] });
    }
  });

  it("leaves a backstory's lists as they were: an indented item is a sibling or goes on with the line above", () => {
    const [bullets] = parseBlocks("- one\n  - one a\n- two");
    expect(bullets).toEqual({ t: "ul", items: [[{ t: "text", v: "one" }], [{ t: "text", v: "one a" }], [{ t: "text", v: "two" }]] });
    const [numbers] = parseBlocks("1. Fill in:\n   - Name");
    expect(numbers).toEqual({ t: "ol", start: 1, items: [[{ t: "text", v: "Fill in:" }, { t: "br" }, { t: "text", v: "- Name" }]] });
  });

  it("leaves a backstory's Markdown as it was: no tables, images or relative links", () => {
    const blocks = parseBlocks("| a | b |\n| - | - |\n| 1 | 2 |\n\n![x](images/a.png) [y](players.md)");
    expect(blocks.map((b) => b.t)).toEqual(["p", "p"]);
    expect(JSON.stringify(blocks)).not.toContain('"image"');
    expect(JSON.stringify(blocks)).not.toContain('"link"');
  });
});

describe("ManualMarkdown", () => {
  it("never renders raw HTML", () => {
    const container = show(
      '# Title\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)> <a href="javascript:x">a</a>\n\n| <b>x</b> |\n| - |\n| <i>y</i> |',
    );
    expect(container.querySelector("script, img, b, i, a[href^='javascript']")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect(container.querySelector("td")?.textContent).toBe("<i>y</i>");
  });

  it("gives headings their own level and anchors", () => {
    const container = show("# Players\n\n## Spending XP & approvals\n\n### Asking for an exception");
    expect(container.querySelector("h1")?.id).toBe("players");
    expect(container.querySelector("h2")?.id).toBe("spending-xp--approvals");
    expect(container.querySelector("h3")?.id).toBe("asking-for-an-exception");
  });

  it("links to other pages and anchors in the app, and out to the web in a new tab", () => {
    const container = show(
      "[Downtimes](players.md#downtimes), [above](#top), [the glossary](glossary.md) and [GitHub](https://github.com/michael-tracey/horatio)",
    );
    const links = [...container.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/help/players#downtimes",
      "/help/players#top",
      "/help/glossary",
      "https://github.com/michael-tracey/horatio",
    ]);
    expect(links[3]!.getAttribute("target")).toBe("_blank");
    expect(links[3]!.getAttribute("rel")).toContain("noopener");
    expect(links[0]!.getAttribute("target")).toBeNull();
  });

  it("shows a link it can't follow as its words", () => {
    const container = show("[a picture](images/x.png)");
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toBe("a picture");
  });

  it("draws images from the bundle, and says when one is missing", () => {
    const container = show("![The sheet tab](./images/players/sheet.png)\n\n![The cart](images/players/cart.png)", {
      images: { "images/players/sheet.png": "/assets/sheet-abc.png" },
    });
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/assets/sheet-abc.png");
    expect(img.getAttribute("alt")).toBe("The sheet tab");
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(container.textContent).toContain("[Missing image: The cart]");
  });

  it("draws nested lists inside their item", () => {
    const container = show("1. Fill in:\n   - Name\n   - Handle\n2. Done.");
    expect(container.querySelectorAll("ol > li")).toHaveLength(2);
    expect([...container.querySelectorAll("ol > li:first-child > ul > li")].map((li) => li.textContent)).toEqual(["Name", "Handle"]);
  });

  it("draws tables and quotes", () => {
    const container = show("> **If your troupe uses this:** feeding.\n\n| Role | Can |\n| --- | --- |\n| Narrator | Answer actions |");
    expect(container.querySelector("blockquote strong")?.textContent).toBe("If your troupe uses this:");
    expect([...container.querySelectorAll("th")].map((th) => th.textContent)).toEqual(["Role", "Can"]);
    expect(container.querySelector("th")?.getAttribute("scope")).toBe("col");
    expect([...container.querySelectorAll("td")].map((td) => td.textContent)).toEqual(["Narrator", "Answer actions"]);
  });

  it("marks the links to the reader's part", () => {
    const container = show("- [Players](players.md)\n- [Custodian](custodian.md)", { highlight: "custodian" });
    const links = [...container.querySelectorAll("a")];
    expect(links[1]!.textContent).toBe("Custodian for you");
    expect(links[0]!.textContent).toBe("Players");
  });
});

describe("Markdown (backstories)", () => {
  it("is unchanged: headings below the page's own, no anchors, no tables or images", () => {
    const { container } = render(<Markdown text={"# Early nights\n\n| a | b |\n| - | - |\n\n![x](images/a.png) [y](players.md)"} />);
    const h3 = container.querySelector("h3")!;
    expect(h3.textContent).toBe("Early nights");
    expect(h3.hasAttribute("id")).toBe(false);
    expect(container.querySelector("table, img, a")).toBeNull();
  });
});
