import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GAP, NO_TAPS, TAPS, cardPath, hasCard, tapped, useSevenTaps } from "./taps";

describe("seven taps", () => {
  it("opens on the seventh tap in a row, and counts again from there", () => {
    let taps = NO_TAPS;
    const opened: number[] = [];
    for (let i = 1; i <= TAPS * 2; i++) {
      const next = tapped(taps, i * 300);
      if (next.open) opened.push(i);
      taps = next;
    }
    expect(opened).toEqual([7, 14]);
  });

  it("starts again after a pause", () => {
    let taps = NO_TAPS;
    for (let i = 0; i < 6; i++) taps = tapped(taps, i * 100);
    expect(taps.count).toBe(6);
    const late = tapped(taps, 500 + GAP + 1);
    expect(late).toMatchObject({ count: 1, open: false });
  });

  it("is only for a vampire with a picture", () => {
    expect(hasCard({ picture: "/p", social_age: "Ancilla" })).toBe(true);
    expect(hasCard({ picture: null, social_age: "Elder" })).toBe(false);
    expect(hasCard({ picture: "/p", social_age: "Ghoul" })).toBe(false);
    expect(hasCard({ picture: "/p", social_age: "Mortal" })).toBe(false);
    expect(cardPath("c1", "t1")).toBe("/print/characters/c1/jyhad?troupe=t1");
  });
});

function Clan() {
  const taps = useSevenTaps("c1");
  return <span onClick={taps}>Tremere</span>;
}

describe("the clan's name", () => {
  beforeEach(() => vi.useFakeTimers({ now: 0, toFake: ["Date", "setTimeout"] }));
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("opens the card on the seventh tap, and not before", () => {
    render(
      <MemoryRouter initialEntries={["/characters/c1"]}>
        <Routes>
          <Route path="/characters/:id" element={<Clan />} />
          <Route path="/print/characters/:id/jyhad" element={<p>The card</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const clan = screen.getByText("Tremere");
    for (let i = 0; i < 6; i++) {
      fireEvent.click(clan);
      act(() => void vi.advanceTimersByTime(400));
    }
    expect(screen.queryByText("The card")).toBeNull();
    fireEvent.click(clan);
    expect(screen.getByText("The card")).toBeTruthy();
  });

  it("doesn't open for taps too far apart", () => {
    render(
      <MemoryRouter initialEntries={["/characters/c1"]}>
        <Routes>
          <Route path="/characters/:id" element={<Clan />} />
          <Route path="/print/characters/:id/jyhad" element={<p>The card</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const clan = screen.getByText("Tremere");
    for (let i = 0; i < 7; i++) {
      fireEvent.click(clan);
      act(() => void vi.advanceTimersByTime(GAP + 100));
    }
    expect(screen.queryByText("The card")).toBeNull();
  });
});
