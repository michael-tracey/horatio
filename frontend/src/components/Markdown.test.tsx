import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { headings, parseBlocks, parseInline } from "../markdown";
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
