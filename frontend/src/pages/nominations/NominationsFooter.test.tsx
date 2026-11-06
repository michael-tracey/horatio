import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Rotation } from "./NominationsFooter";
import { ROTATE_MS } from "./nominations";

const items = [
  { id: "1", text: "Corin's toast was perfect", month: "October 2026" },
  { id: "2", text: "Thank you for the ball", month: "October 2026" },
  { id: "3", text: "Everyone, for a kind night", month: "November 2026" },
];

function motion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
}

const shown = () => screen.getByRole("complementary", { name: "Player Nominations" }).querySelector("blockquote")?.textContent;

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0);
  motion(false);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the footer of starred nominations", () => {
  it("shows one at a time with its month, never an author, and moves on every so often", () => {
    render(<Rotation items={items} />);
    expect(shown()).toBe("“Corin's toast was perfect”");
    expect(screen.getByText("Player Nominations, October 2026")).not.toBeNull();
    act(() => vi.advanceTimersByTime(ROTATE_MS - 1));
    expect(shown()).toBe("“Corin's toast was perfect”");
    act(() => vi.advanceTimersByTime(1));
    expect(shown()).toBe("“Thank you for the ball”");
    act(() => vi.advanceTimersByTime(2 * ROTATE_MS));
    // Round again after the last.
    expect(shown()).toBe("“Corin's toast was perfect”");
  });

  it("starts somewhere new on each page load", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.9);
    render(<Rotation items={items} />);
    expect(shown()).toBe("“Everyone, for a kind night”");
    expect(screen.getByText("Player Nominations, November 2026")).not.toBeNull();
  });

  it("stays put when paused, or while the pointer is on it, and Next moves on by hand", () => {
    render(<Rotation items={items} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("button", { name: "Play" }).getAttribute("aria-pressed")).toBe("true");
    act(() => vi.advanceTimersByTime(5 * ROTATE_MS));
    expect(shown()).toBe("“Corin's toast was perfect”");
    fireEvent.click(screen.getByRole("button", { name: "Next nomination" }));
    expect(shown()).toBe("“Thank you for the ball”");
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    fireEvent.mouseEnter(screen.getByRole("complementary"));
    act(() => vi.advanceTimersByTime(2 * ROTATE_MS));
    expect(shown()).toBe("“Thank you for the ball”");
    fireEvent.mouseLeave(screen.getByRole("complementary"));
    act(() => vi.advanceTimersByTime(ROTATE_MS));
    expect(shown()).toBe("“Everyone, for a kind night”");
  });

  it("never moves by itself for someone who asks for less motion", () => {
    motion(true);
    render(<Rotation items={items} />);
    act(() => vi.advanceTimersByTime(10 * ROTATE_MS));
    expect(shown()).toBe("“Corin's toast was perfect”");
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Next nomination" }));
    expect(shown()).toBe("“Thank you for the ball”");
  });

  it("can be skipped, and isn't read out as it changes", () => {
    render(<Rotation items={items} />);
    const skip = screen.getByRole("link", { name: "Skip the nominations" });
    expect(document.getElementById(skip.getAttribute("href")!.slice(1))).not.toBeNull();
    expect(screen.getByRole("complementary").closest("[aria-live]")).toBeNull();
  });

  it("has nothing to turn with one alone", () => {
    render(<Rotation items={items.slice(0, 1)} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
