import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StepButton } from "./StepButton";

afterEach(cleanup);

describe("StepButton", () => {
  it("does its step when it can", () => {
    const step = vi.fn();
    render(<StepButton label="Lower Brawl" onClick={step}>−</StepButton>);
    fireEvent.click(screen.getByRole("button", { name: "Lower Brawl" }));
    expect(step).toHaveBeenCalledOnce();
  });

  it("is plainly disabled when it can't, and there is no reason to give", () => {
    render(<StepButton label="Raise Brawl" disabled onClick={() => {}}>+</StepButton>);
    expect((screen.getByRole("button", { name: "Raise Brawl" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("with a reason, stays tappable, and a tap shows the reason instead of stepping", () => {
    const step = vi.fn();
    const why = "Accepted by the home troupe; only storytellers can take these dots away.";
    render(
      <StepButton label="Lower Brawl" disabled reason={why} onClick={step}>
        −
      </StepButton>,
    );
    const button = screen.getByRole("button", { name: "Lower Brawl" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(button.getAttribute("aria-disabled")).toBe("true");
    const reason = document.getElementById(button.getAttribute("aria-describedby")!)!;
    expect(reason.textContent).toBe(why);
    expect(reason.className).toContain("hidden");
    fireEvent.click(button);
    expect(step).not.toHaveBeenCalled();
    expect(reason.className).toContain("block");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(reason.className).toContain("hidden");
  });
});
