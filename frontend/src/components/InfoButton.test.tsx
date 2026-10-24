import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { InfoButton } from "./InfoButton";

afterEach(cleanup);

function setup() {
  render(
    <div>
      <p>
        Skills
        <InfoButton label="About Skills">What the character has learned to do.</InfoButton>
      </p>
      <button>Elsewhere</button>
    </div>,
  );
  const button = screen.getByRole("button", { name: "About Skills" });
  const popover = () => document.getElementById(button.getAttribute("aria-controls")!);
  return { button, popover };
}

describe("InfoButton", () => {
  it("starts closed", () => {
    const { button, popover } = setup();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(popover()).toBeNull();
  });

  it("opens on a press, and closes when pressed again", () => {
    const { button, popover } = setup();
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(popover()!.textContent).toBe("What the character has learned to do.");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(popover()).toBeNull();
  });

  it("closes on Escape, and gives focus back to the button", () => {
    const { button, popover } = setup();
    fireEvent.click(button);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(popover()).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("closes on a press outside, but not on a press inside", () => {
    const { button, popover } = setup();
    fireEvent.click(button);
    fireEvent.pointerDown(popover()!);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    fireEvent.pointerDown(screen.getByRole("button", { name: "Elsewhere" }));
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(popover()).toBeNull();
  });

  it("ignores Escape and outside presses while closed", () => {
    const { button } = setup();
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.pointerDown(document.body);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).not.toBe(button);
  });

  it("ties the button to its popover", () => {
    const { button, popover } = setup();
    fireEvent.click(button);
    expect(popover()!.id).toBe(button.getAttribute("aria-controls"));
  });
});
