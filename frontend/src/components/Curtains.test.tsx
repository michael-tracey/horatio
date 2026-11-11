import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CurtainsHost, drawCurtains, MOVING, STILL } from "./Curtains";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));
const curtains = () => screen.queryByTestId("curtains");

function reduceMotion(on: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: on && query.includes("reduce"), media: query }));
}

describe("the curtains", () => {
  it("close, make the change while closed, then open and go", () => {
    reduceMotion(false);
    render(<CurtainsHost />);
    const change = vi.fn();
    act(() => drawCurtains(change));
    expect(curtains()!.dataset.phase).toBe("closing");
    expect(curtains()!.querySelectorAll(".curtain")).toHaveLength(2);
    expect(document.body.style.overflow).toBe("hidden");
    // A second ask while they run is the same run.
    act(() => drawCurtains(change));

    wait(MOVING.close - 1);
    expect(change).not.toHaveBeenCalled();
    wait(1);
    expect(change).toHaveBeenCalledTimes(1);
    expect(curtains()!.dataset.phase).toBe("closed");
    wait(MOVING.hold);
    expect(curtains()!.dataset.phase).toBe("opening");
    wait(MOVING.open);
    expect(curtains()).toBeNull();
    expect(change).toHaveBeenCalledTimes(1);
    expect(document.body.style.overflow).toBe("");
  });

  it("fade to velvet and back instead, with reduced motion", () => {
    reduceMotion(true);
    render(<CurtainsHost />);
    const change = vi.fn();
    act(() => drawCurtains(change));
    expect(curtains()!.querySelector(".curtain-fade")).toBeTruthy();
    expect(curtains()!.querySelector(".curtain")).toBeNull();
    wait(STILL.close);
    expect(change).toHaveBeenCalledTimes(1);
    wait(STILL.hold + STILL.open);
    expect(curtains()).toBeNull();
  });
});
