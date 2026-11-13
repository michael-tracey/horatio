import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeatureSettings } from "./FeatureSettings";

afterEach(cleanup);

function show(at: string) {
  render(
    <MemoryRouter initialEntries={[at]}>
      <FeatureSettings>
        <p>Who may settle a boon</p>
      </FeatureSettings>
    </MemoryRouter>,
  );
  return screen.getByText("Settings").closest("details")!;
}

describe("a feature's folded Settings (#784)", () => {
  it("is folded when the tab is opened", () => {
    expect(show("/troupes/t1/boons").open).toBe(false);
  });

  it("opens when the Features list's Settings link lands on it, and is scrolled to", () => {
    const scroll = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: scroll, configurable: true });
    try {
      expect(show("/troupes/t1/boons#settings").open).toBe(true);
      expect(scroll).toHaveBeenCalled();
    } finally {
      delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });
});
