import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { PageTabs } from "./ui";

afterEach(cleanup);

const tabs = [
  { to: "/rules", label: "Checks", end: true },
  { to: "/rules/house-traits", label: "House merits and flaws" },
  { to: "/rules/teachers", label: "Teachers" },
];

describe("PageTabs", () => {
  it("wraps onto more rows instead of scrolling sideways, never inside a label (#649)", () => {
    render(
      <MemoryRouter initialEntries={["/rules/teachers"]}>
        <PageTabs label="House rules" tabs={tabs} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "House rules" });
    const row = nav.firstElementChild as HTMLElement;
    for (const box of [nav, row]) {
      expect(box.className).not.toMatch(/overflow-x-(auto|scroll)/);
      expect(box.className).not.toContain("nowrap");
    }
    expect(row.className).toContain("flex-wrap");
    for (const link of screen.getAllByRole("link")) expect(link.className).toContain("whitespace-nowrap");
  });

  it("marks the open tab", () => {
    render(
      <MemoryRouter initialEntries={["/rules/teachers"]}>
        <PageTabs label="House rules" tabs={tabs} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Teachers" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Checks" }).getAttribute("aria-current")).toBeNull();
  });
});
