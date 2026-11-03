import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionMenu, MenuGroup, MenuItem } from "./ActionMenu";

afterEach(cleanup);

function setup() {
  const chosen = vi.fn();
  render(
    <div>
      <ActionMenu label="Actions for Ines">
        <MenuGroup label="Help">
          <MenuItem onSelect={() => chosen("view")}>View as…</MenuItem>
          <MenuItem disabled>Characters</MenuItem>
          <MenuItem onSelect={() => chosen("email")}>Change email…</MenuItem>
        </MenuGroup>
        <MenuGroup label="Weightier">
          <MenuItem onSelect={() => chosen("suspend")}>Suspend…</MenuItem>
        </MenuGroup>
      </ActionMenu>
      <button>Elsewhere</button>
    </div>,
  );
  const button = screen.getByRole("button", { name: "Actions for Ines" });
  const menu = () => screen.queryByRole("menu");
  const item = (name: string) => screen.getByRole("menuitem", { name });
  return { button, menu, item, chosen };
}

describe("ActionMenu", () => {
  it("is a closed menu button to begin with", () => {
    const { button, menu } = setup();
    expect(button.getAttribute("aria-haspopup")).toBe("menu");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(menu()).toBeNull();
  });

  it("opens on a press, at the first item, and closes when pressed again", () => {
    const { button, menu, item } = setup();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(menu()).not.toBeNull();
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["View as…", "Characters", "Change email…", "Suspend…"]);
    expect(screen.getAllByRole("group").map((g) => g.getAttribute("aria-label"))).toEqual(["Help", "Weightier"]);
    expect(document.activeElement).toBe(item("View as…"));
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(menu()).toBeNull();
  });

  it("closes on Escape, and gives focus back to the button", () => {
    const { button, menu, item } = setup();
    fireEvent.click(button);
    fireEvent.keyDown(item("View as…"), { key: "Escape" });
    expect(menu()).toBeNull();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(button);
  });

  it("closes on a press outside, but not on a press inside", () => {
    const { button, menu, item } = setup();
    fireEvent.click(button);
    fireEvent.pointerDown(item("Change email…"));
    expect(menu()).not.toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(menu()).toBeNull();
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("moves between the items with the arrow keys, Home and End, passing over one that can't be chosen", () => {
    const { button, item } = setup();
    fireEvent.click(button);
    const key = (k: string) => fireEvent.keyDown(document.activeElement!, { key: k });
    key("ArrowDown");
    expect(document.activeElement).toBe(item("Change email…"));
    key("ArrowDown");
    expect(document.activeElement).toBe(item("Suspend…"));
    key("ArrowDown");
    expect(document.activeElement).toBe(item("View as…"));
    key("ArrowUp");
    expect(document.activeElement).toBe(item("Suspend…"));
    key("Home");
    expect(document.activeElement).toBe(item("View as…"));
    key("End");
    expect(document.activeElement).toBe(item("Suspend…"));
  });

  it("opens from the keyboard: ↓ at the first item, ↑ at the last", () => {
    const { button, menu, item } = setup();
    fireEvent.keyDown(button, { key: "ArrowDown" });
    expect(document.activeElement).toBe(item("View as…"));
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(menu()).toBeNull();
    fireEvent.keyDown(button, { key: "ArrowUp" });
    expect(document.activeElement).toBe(item("Suspend…"));
  });

  it("closes once an item is chosen, does it, and gives focus back to the button", () => {
    const { button, menu, item, chosen } = setup();
    fireEvent.click(button);
    fireEvent.click(item("Change email…"));
    expect(chosen).toHaveBeenCalledWith("email");
    expect(menu()).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("closes when Tab leaves it", () => {
    const { button, menu } = setup();
    fireEvent.click(button);
    fireEvent.keyDown(document.activeElement!, { key: "Tab" });
    expect(menu()).toBeNull();
  });

  it("slides back on screen when it would open off the left edge of a phone", () => {
    const width = vi.spyOn(document.documentElement, "clientWidth", "get").mockReturnValue(390);
    const box = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: -120, right: 136, top: 0, bottom: 0, width: 256, height: 0, x: -120, y: 0, toJSON: () => ({}) });
    const { button, menu } = setup();
    fireEvent.click(button);
    expect(menu()!.style.transform).toBe("translateX(128px)");
    width.mockRestore();
    box.mockRestore();
  });

  it("ignores Escape and presses outside while closed", () => {
    const { button, menu } = setup();
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.pointerDown(document.body);
    expect(menu()).toBeNull();
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });
});
