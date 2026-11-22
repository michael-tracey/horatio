import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { figureMarkdown, headings, parseBlocks, parseInline } from "../markdown";
import { Markdown } from "./Markdown";

afterEach(cleanup);

describe("parseInline", () => {
  it("reads emphasis, code and links", () => {
    expect(parseInline("a **bold** and *soft* `x`")).toEqual([
      { t: "text", v: "a " },
      { t: "strong", c: [{ t: "text", v: "bold" }] },
      { t: "text", v: " and " },
      { t: "em", c: [{ t: "text", v: "soft" }] },
      { t: "text", v: " " },
      { t: "code", v: "x" },
    ]);
    expect(parseInline("[the city](https://example.com)")).toEqual([{ t: "link", href: "https://example.com", c: [{ t: "text", v: "the city" }] }]);
  });

  it("leaves a link to anything but the web or email as text", () => {
    expect(parseInline("[x](javascript:alert(1))")).toEqual([{ t: "text", v: "[x](javascript:alert(1))" }]);
  });

  it("keeps underscores inside words and escaped marks", () => {
    expect(parseInline("snake_case_name")).toEqual([{ t: "text", v: "snake_case_name" }]);
    expect(parseInline("\\*not em\\*")).toEqual([{ t: "text", v: "*not em*" }]);
    expect(parseInline("2 * 3 * 4")).toEqual([{ t: "text", v: "2 * 3 * 4" }]);
  });
});

describe("parseBlocks", () => {
  it("reads headings, lists, quotes and rules, and leaves out comment lines", () => {
    const blocks = parseBlocks("# Title\n\n<!-- questions:1 -->\n- one\n- two\n\n1. first\n2. second\n\n> said\n\n---\nlast line\nnext line");
    expect(blocks.map((b) => b.t)).toEqual(["heading", "ul", "ol", "quote", "hr", "p"]);
    expect(blocks[5]).toEqual({ t: "p", c: [{ t: "text", v: "last line" }, { t: "br" }, { t: "text", v: "next line" }] });
  });

  it("lists the headings feedback can be on", () => {
    expect(headings("# Early\n\ntext\n\n## My **sire**\n\n##\n")).toEqual(["Early", "My sire"]);
  });
});

describe("Markdown", () => {
  it("never renders raw HTML", () => {
    const { container } = render(<Markdown text={'<script>alert(1)</script>\n\n<b onclick="x">bold</b> <img src=x onerror=alert(1)>'} />);
    expect(container.querySelector("script, b, img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("renders headings below the page's own, and safe links", () => {
    const { container } = render(<Markdown text={"# Early nights\n\nSee [the map](https://example.com/map)."} />);
    expect(container.querySelector("h3")?.textContent).toBe("Early nights");
    const link = container.querySelector("a")!;
    expect(link.getAttribute("href")).toBe("https://example.com/map");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});

describe("a blog article's pictures (#1163)", () => {
  const ID = "0196f2a4-3333-7000-8000-000000000003";
  const LINE = `![Candles on a long table](blog-picture:${ID} "The Elysium at midnight")`;

  it("are read only when asked for, each on a line of its own", () => {
    expect(parseBlocks(`Before\n${LINE}\nAfter`, false, { pictures: true })).toEqual([
      { t: "p", c: [{ t: "text", v: "Before" }] },
      { t: "figure", id: ID, alt: "Candles on a long table", caption: "The Elysium at midnight" },
      { t: "p", c: [{ t: "text", v: "After" }] },
    ]);
    expect(parseBlocks(`![Alone](blog-picture:${ID})`, false, { pictures: true })).toEqual([{ t: "figure", id: ID, alt: "Alone", caption: "" }]);
    // Troupe news, backstories and the rest: the same line is text.
    expect(parseBlocks(LINE).map((b) => b.t)).toEqual(["p"]);
    expect(parseBlocks(`> ${LINE}`, false, { pictures: true })[0]).toMatchObject({ t: "quote", c: [{ t: "p" }] });
    expect(parseBlocks(`Text ${LINE}`, false, { pictures: true }).map((b) => b.t)).toEqual(["p"]);
  });

  it("are only the blog's own, never an outside address or one without what it shows", () => {
    for (const line of [
      "![A logo](https://example.com/logo.png)",
      `![A logo](/api/blog/body-pictures/${ID}/600.webp)`,
      "![A logo](blog-picture:javascript:alert(1))",
      `![A logo](blog-picture:${ID.toUpperCase()})`,
      `![](blog-picture:${ID})`,
    ]) {
      expect(parseBlocks(line, false, { pictures: true }).map((b) => b.t), line).toEqual(["p"]);
    }
  });

  it("write back as the same picture, whatever is in what they say", () => {
    const line = figureMarkdown({ id: ID, alt: "A ]tricky[ \\ one\nover two lines", caption: 'Say "cheese"' });
    expect(line).toBe(`![A \\]tricky[ \\\\ one over two lines](blog-picture:${ID} "Say \\"cheese\\"")`);
    expect(parseBlocks(line, false, { pictures: true })).toEqual([{ t: "figure", id: ID, alt: "A ]tricky[ \\ one over two lines", caption: 'Say "cheese"' }]);
    expect(figureMarkdown({ id: ID, alt: "  " })).toBe(`![Picture](blog-picture:${ID})`);
  });

  it("show at the two sizes, loaded as they come near, with the caption under them", () => {
    const { container } = render(<Markdown text={`Before\n\n${LINE}`} pictures />);
    const figure = container.querySelector("figure")!;
    const img = figure.querySelector("img")!;
    expect(img.getAttribute("src")).toBe(`/api/blog/body-pictures/${ID}/1200.webp`);
    expect(img.getAttribute("srcset")).toBe(`/api/blog/body-pictures/${ID}/600.webp 600w, /api/blog/body-pictures/${ID}/1200.webp 1200w`);
    expect(img.getAttribute("sizes")).toBeTruthy();
    expect(img.getAttribute("alt")).toBe("Candles on a long table");
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.className).toContain("w-full");
    expect(figure.querySelector("figcaption")!.textContent).toBe("The Elysium at midnight");
    expect(render(<Markdown text={`![Alone](blog-picture:${ID})`} pictures />).container.querySelector("figcaption")).toBeNull();
  });

  it("are text anywhere else", () => {
    const { container } = render(<Markdown text={LINE} />);
    expect(container.querySelector("img, figure")).toBeNull();
    expect(container.textContent).toContain("blog-picture:");
  });
});
