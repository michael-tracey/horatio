import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { atGameCrumbs, Breadcrumb } from "./Breadcrumb";

afterEach(cleanup);

describe("Breadcrumb", () => {
  it("links back to the troupe and its At game tab, in order", () => {
    render(
      <MemoryRouter>
        <Breadcrumb crumbs={[...atGameCrumbs("t1", "The Night Court"), { label: "Scenes", to: "/play/troupes/t1/scenes" }]} />
      </MemoryRouter>,
    );
    const links = within(screen.getByRole("navigation", { name: "Breadcrumb" })).getAllByRole("link");
    expect(links.map((l) => [l.textContent, l.getAttribute("href")])).toEqual([
      ["The Night Court", "/troupes/t1"],
      ["At game", "/troupes/t1/play"],
      ["Scenes", "/play/troupes/t1/scenes"],
    ]);
  });

  it("names the troupe plainly until its name has loaded", () => {
    render(
      <MemoryRouter>
        <Breadcrumb crumbs={atGameCrumbs("t1", undefined)} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Troupe" }).getAttribute("href")).toBe("/troupes/t1");
  });
});
