import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SiteMenu } from "./Layout";

afterEach(cleanup);

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function setup({ isCustodian = false, at = "/characters" } = {}) {
  const onSignOut = vi.fn();
  render(
    <MemoryRouter initialEntries={[at]}>
      <SiteMenu name="Ines Ferreira-Valadares" isCustodian={isCustodian} onSignOut={onSignOut} />
      <button>Elsewhere</button>
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
  const button = screen.getByRole("button", { name: "Menu" });
  const nav = () => screen.queryByRole("navigation", { name: "Main" });
  return { button, nav, onSignOut };
}

describe("SiteMenu", () => {
  it("is a closed menu button to begin with", () => {
    const { button, nav } = setup();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(nav()).toBeNull();
  });

  it("opens to the bar's links, one to a line, with focus on the first", () => {
    const { button, nav } = setup();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(button.getAttribute("aria-controls")).toBe(nav()?.parentElement?.id);
    const names = screen.getAllByRole("link").map((a) => a.getAttribute("aria-label") ?? a.textContent);
    expect(names).toEqual(["Characters", "Troupes", "Rules reference", "Help", "Your account: Ines Ferreira-Valadares"]);
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("link", { name: "Characters" }));
  });

  it("has Custodian and says so for the custodian", () => {
    const { button } = setup({ isCustodian: true });
    fireEvent.click(button);
    expect(screen.getByRole("link", { name: "Custodian" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Your account/ }).textContent).toContain("(custodian)");
  });

  it("marks the page you are on, and Troupes within a troupe's downtime cycle", () => {
    const { button } = setup({ at: "/troupes/t1/downtimes/abc" });
    fireEvent.click(button);
    expect(screen.getByRole("link", { name: "Troupes" }).getAttribute("class")).toContain("text-parchment");
    expect(screen.getByRole("link", { name: "Characters" }).getAttribute("class")).not.toContain("bg-ash/40 text-parchment");
  });

  it("closes on choosing a link, and goes there", () => {
    const { button, nav } = setup();
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("link", { name: "Troupes" }));
    expect(nav()).toBeNull();
    expect(screen.getByTestId("where").textContent).toBe("/troupes");
  });

  it("closes on Escape, giving focus back to the button", () => {
    const { button, nav } = setup();
    fireEvent.click(button);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(nav()).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("closes on a press outside it", () => {
    const { button, nav } = setup();
    fireEvent.click(button);
    fireEvent.mouseDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(nav()).toBeNull();
  });

  it("signs out from the menu", () => {
    const { button, nav, onSignOut } = setup();
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(onSignOut).toHaveBeenCalledOnce();
    expect(nav()).toBeNull();
  });
});
