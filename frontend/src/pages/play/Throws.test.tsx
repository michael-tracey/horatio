import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThrowsTab } from "./Throws";
import { useChallenge } from "./Challenge";
import { load } from "./challenge";

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

/** The Throws tab with a pool loaded from the Pools tab, as the Play View does (#698). */
function Loaded({ pool, total, spendWillpower }: { pool: Parameters<typeof load>[0]; total: number; spendWillpower?: () => void }) {
  const challenging = useChallenge();
  if (!challenging.challenge) {
    challenging.update(() => load(pool, total, "Physical 5 + Brawl 7"));
    return null;
  }
  return <ThrowsTab challenging={challenging} willpower={3} spendWillpower={spendWillpower} />;
}

function loaded(props: Parameters<typeof Loaded>[0]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Loaded {...props} />
    </QueryClientProvider>,
  );
}

const brawl = { key: "attack:Brawl", name: "Brawl attack", parts: [{ label: "Physical", value: 5 }, { label: "Brawl", value: 7 }], versus: "Physical + Dodge" };
const dodge = { key: "dodge", name: "Dodge", parts: [{ label: "Physical", value: 4 }, { label: "Dodge", value: 2 }], versus: null };

/** Throws, then taps that the other side showed the same: a tie, whatever the phone threw. */
function throwATie() {
  fireEvent.click(screen.getByRole("button", { name: "Throw" }));
  const mine = screen.getByRole("img", { name: THROWN }).getAttribute("aria-label");
  fireEvent.click(screen.getByRole("button", { name: `They showed ${mine}` }));
}

describe("a pool thrown from the Pools tab", () => {
  it("says what the pools mean before the throw: an overbid, and who a tie goes to", () => {
    motion(true);
    loaded({ pool: brawl, total: 12 });
    expect(screen.getByText("Throwing Brawl attack")).toBeTruthy();
    expect(screen.getByText("Ask them for their pool, and enter it to throw this challenge.")).toBeTruthy();
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "6" } });
    expect(screen.getByText(/Overbid: your pool is at least double theirs/)).toBeTruthy();
    expect(screen.getByText("A tie goes to you: your 12 is greater than their 6.")).toBeTruthy();
  });

  it("takes the throw and what they showed as the test, and gives the result", () => {
    motion(true);
    loaded({ pool: brawl, total: 12 });
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "6" } });
    throwATie();
    expect(screen.getByRole("status").textContent).toContain("Success");
    expect(screen.getByRole("list", { name: "Tests" }).children).toHaveLength(1);
    // Won on a tie: they may retest, and it isn't exceptional.
    expect(screen.getByRole("status").textContent).not.toContain("Exceptional");
    expect(screen.getByRole("button", { name: "They retest with Willpower" })).toBeTruthy();
  });

  it("spends Willpower from the tracker for this player's retest", () => {
    motion(true);
    const spendWillpower = vi.fn();
    loaded({ pool: dodge, total: 6, spendWillpower });
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "12" } });
    expect(screen.getByText(/They can overbid/)).toBeTruthy();
    throwATie();
    expect(screen.getByRole("status").textContent).toContain("You lose");
    fireEvent.click(screen.getByRole("button", { name: /Spend 1 Willpower to retest/ }));
    expect(spendWillpower).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Retest with Willpower: throw again.")).toBeTruthy();
    throwATie();
    expect(screen.getByRole("list", { name: "Tests" }).children).toHaveLength(2);
    // Lost again on pools: one Willpower retest a challenge, so only a merit is left.
    expect(screen.getByRole("status").textContent).toContain("You lose");
    expect(screen.queryByRole("button", { name: /Willpower/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Retest with a merit" })).toBeTruthy();
  });
});

describe("throwing by flipping the phone (#669)", () => {
  afterEach(() => localStorage.clear());

  /** One reading from the phone's orientation sensor. */
  function orient(beta: number | null, gamma: number | null = 0) {
    act(() => void window.dispatchEvent(Object.assign(new Event("deviceorientation"), { beta, gamma })));
  }

  function flipOver() {
    for (const beta of [0, 60, 120, 180, 120, 60, 0]) orient(beta);
  }

  it("offers nothing where the browser gives no readings, as desktops do", () => {
    motion(false);
    shown();
    orient(null, null);
    expect(screen.queryByRole("checkbox", { name: "Throw by flipping" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Turn on flipping the phone" })).toBeNull();
  });

  it("offers the switch once the sensor reads, and a flip throws at once, with a buzz", () => {
    motion(false);
    const vibrate = vi.fn();
    vi.stubGlobal("navigator", { ...navigator, vibrate });
    shown();
    orient(0);
    expect((screen.getByRole("checkbox", { name: "Throw by flipping" }) as HTMLInputElement).checked).toBe(true);
    flipOver();
    // No count-in: the screen was face down, so the throw shows as it comes up.
    expect(screen.queryByText("Rock…")).toBeNull();
    expect(screen.getByRole("img", { name: THROWN })).toBeTruthy();
    expect(vibrate).toHaveBeenCalledOnce();
    expect(screen.getByRole("list").children).toHaveLength(1);
  });

  it("doesn't throw by flipping once switched off, and remembers that on this device", () => {
    motion(true);
    shown();
    orient(0);
    fireEvent.click(screen.getByRole("checkbox", { name: "Throw by flipping" }));
    flipOver();
    expect(screen.queryByRole("img", { name: THROWN })).toBeNull();
    expect(localStorage.getItem("horatio.throwByFlipping")).toBe("off");
  });

  /** A touch phone, as iOS reports: its pointer is a finger. */
  function touch(reduce = true) {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: (reduce && query.includes("reduce")) || query.includes("coarse"), media: query, addEventListener() {}, removeEventListener() {} }));
  }

  it("asks first on an iPhone that sends nothing, from a tap, and then throws by flipping", async () => {
    vi.useFakeTimers();
    touch();
    const requestPermission = vi.fn(() => Promise.resolve("granted"));
    vi.stubGlobal("DeviceOrientationEvent", { requestPermission });
    shown();
    // iOS sends nothing before it's asked, so after a moment the tab offers to ask.
    expect(screen.queryByRole("button", { name: "Turn on flipping the phone" })).toBeNull();
    act(() => void vi.advanceTimersByTime(1500));
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Turn on flipping the phone" })));
    expect(requestPermission).toHaveBeenCalledOnce();
    expect(localStorage.getItem("horatio.flipAsked")).toBe("granted");
    orient(0);
    flipOver();
    expect(screen.getByRole("img", { name: THROWN })).toBeTruthy();
  });

  it("says where to allow it when the iPhone said no", async () => {
    vi.useFakeTimers();
    touch();
    vi.stubGlobal("DeviceOrientationEvent", { requestPermission: () => Promise.resolve("denied") });
    shown();
    act(() => void vi.advanceTimersByTime(1500));
    await act(async () => void fireEvent.click(screen.getByRole("button", { name: "Turn on flipping the phone" })));
    expect(screen.getByText(/allow Motion & Orientation Access/)).toBeTruthy();
  });

  it("never offers to ask on a desktop, even where the browser could ask", () => {
    vi.useFakeTimers();
    motion(true);
    vi.stubGlobal("DeviceOrientationEvent", { requestPermission: () => Promise.resolve("granted") });
    shown();
    act(() => void vi.advanceTimersByTime(3000));
    expect(screen.queryByRole("button", { name: "Turn on flipping the phone" })).toBeNull();
  });

  it("needs no asking where readings come anyway, as on Android and Chrome", () => {
    touch();
    vi.stubGlobal("DeviceOrientationEvent", { requestPermission: () => Promise.resolve("granted") });
    shown();
    orient(0);
    expect(screen.queryByRole("button", { name: "Turn on flipping the phone" })).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Throw by flipping" })).toBeTruthy();
  });

  it("is a test in a challenge from the Pools tab, like the button", () => {
    motion(true);
    loaded({ pool: brawl, total: 12 });
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "6" } });
    orient(0);
    flipOver();
    expect(screen.getByRole("region", { name: "What they showed" })).toBeTruthy();
  });
});
