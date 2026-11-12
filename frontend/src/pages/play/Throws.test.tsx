import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThrowsTab } from "./Throws";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

function motion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: reduce && query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
}

function shown() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ThrowsTab />
    </QueryClientProvider>,
  );
}

const THROWN = /^(Rock|Paper|Scissors)$/;

describe("the Throws tab", () => {
  it("shows the throw straight away with reduced motion", () => {
    motion(true);
    shown();
    fireEvent.click(screen.getByRole("button", { name: "Throw" }));
    expect(screen.queryByText("Rock…")).toBeNull();
    expect(screen.getByRole("img", { name: THROWN })).toBeTruthy();
    expect(screen.getByRole("list").children).toHaveLength(1);
  });

  it("counts in rock, paper, scissors for about a second, then shows the throw", () => {
    vi.useFakeTimers();
    motion(false);
    shown();
    const button = screen.getByRole("button", { name: "Throw" });
    fireEvent.click(button);
    expect(screen.getByText("Rock…")).toBeTruthy();
    expect(screen.queryByRole("img", { name: THROWN })).toBeNull();
    // A second press while counting in throws nothing more.
    fireEvent.click(button);
    act(() => void vi.advanceTimersByTime(330));
    expect(screen.getByText("Paper…")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(330));
    expect(screen.getByText("Scissors…")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(330));
    expect(screen.getByRole("img", { name: THROWN })).toBeTruthy();
    expect(screen.getByRole("list").children).toHaveLength(1);
  });

  it("keeps the last three throws for the browser tab, through leaving the tab", () => {
    motion(true);
    shown();
    for (let i = 0; i < 4; i++) fireEvent.click(screen.getByRole("button", { name: "Throw" }));
    expect(screen.getByRole("list").children).toHaveLength(3);
    const shownThrow = screen.getByRole("img", { name: THROWN }).getAttribute("aria-label");
    cleanup();
    shown();
    expect(screen.getByRole("list").children).toHaveLength(3);
    expect(screen.getByRole("img", { name: THROWN }).getAttribute("aria-label")).toBe(shownThrow);
  });
});
