import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { WrittenRuleOut } from "../../api/types";
import { bySection, ruleAnchor, ruleLink, searchText, sectionLabel, sectionsInUse } from "./writtenRules";
import { WrittenRulesList } from "./WrittenRulesList";
import { bodyOf, draftOf } from "./WrittenRulesSection";

afterEach(cleanup);

const rule = (id: string, section: string, title: string, more: Partial<WrittenRuleOut> = {}): WrittenRuleOut => ({
  id,
  section,
  title,
  body: "",
  position: 1,
  trait: null,
  page: null,
  ...more,
});

const rules = [
  rule("w", "", "Welcome"),
  rule("c", "Skills", "Crafts difficulties", { body: "Crafts tests are **Mental**." }),
  rule("p", "Skills", "Performance difficulties", { trait: { splat: "vampire", category: "skills", name: "Performance" }, page: "92" }),
  rule("h", "Status", "The Harpy vote"),
];

describe("written rules", () => {
  it("are grouped by section in the order given", () => {
    expect(bySection(rules).map((s) => [s.section, s.rules.map((r) => r.id)])).toEqual([
      ["", ["w"]],
      ["Skills", ["c", "p"]],
      ["Status", ["h"]],
    ]);
    expect(sectionLabel("")).toBe("General");
    expect(sectionsInUse(rules)).toEqual(["Skills", "Status"]);
  });

  it("link to their place on the House rules tab", () => {
    expect(ruleLink("t1", "c")).toBe(`/troupes/t1/house-rules#${ruleAnchor("c")}`);
  });

  it("are searched by title, section, body and trait", () => {
    expect(searchText(rules[2]!)).toBe("performance difficulties skills performance");
    expect(searchText(rules[1]!)).toContain("mental");
  });

  it("send a trait only with its category and name, and no empty page", () => {
    const draft = draftOf(rules[2]!);
    expect(bodyOf(draft)).toEqual({
      section: "Skills",
      title: "Performance difficulties",
      body: "",
      trait: { splat: "vampire", category: "skills", name: "Performance" },
      page: "92",
    });
    expect(bodyOf({ ...draft, trait: " ", page: "  ", title: " Crafts " })).toMatchObject({ trait: null, page: null, title: "Crafts" });
  });
});

describe("WrittenRulesList", () => {
  it("lists contents linking to each rule, then each section's rules with their bodies", () => {
    render(
      <MemoryRouter>
        <WrittenRulesList rules={rules} troupeId="t1" />
      </MemoryRouter>,
    );
    const contents = screen.getByRole("navigation", { name: "Contents" });
    expect(contents.querySelectorAll("a")).toHaveLength(4);
    expect(screen.getByRole("link", { name: "Crafts difficulties" }).getAttribute("href")).toBe(`#${ruleAnchor("c")}`);
    expect(screen.getByRole("heading", { name: "Skills" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "General" })).toBeTruthy();
    expect(screen.getByText("Mental").tagName).toBe("STRONG");
    expect(document.getElementById(ruleAnchor("p"))?.textContent).toContain("About Performance, see p. 92.");
    expect(screen.getByRole("link", { name: "Performance" }).getAttribute("href")).toBe("/rules?category=skills&troupe=t1&q=Performance");
  });

  it("names a trait without a link for someone not signed in, and has no contents for one rule", () => {
    render(
      <MemoryRouter>
        <WrittenRulesList rules={[rules[2]!]} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("navigation", { name: "Contents" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Performance" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Skills" })).toBeTruthy();
  });
});
