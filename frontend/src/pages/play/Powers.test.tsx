import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PowerSwitch } from "../../api/types";
import { PowersBanner, PowersList } from "./Powers";
import { switchKey } from "./powers";

afterEach(cleanup);

const power = (over: Partial<PowerSwitch>): PowerSwitch => ({
  key: "Celerity",
  name: "Celerity",
  origin: "Celerity",
  form: false,
  combines: [],
  page: "p. 121",
  changes: [],
  notes: ["For the turn: 1 Blood activates every Celerity power you have."],
  added: [],
  health: [],
  attributes: [],
  focuses: [],
  blood_per_turn: 0,
  blood_half: false,
  on: false,
  options: [],
  picked: [],
  turned_on: 0,
  kept: false,
  normal_form_only: false,
  counts_as_form: false,
  paused: false,
  ...over,
});

const quickness = { source: "Quickness", page: "p. 214", note: "An extra round of actions, taken in the third Celerity round." };
const earthControl = { source: "Earth Control", page: "p. 221", note: "Move underground at your normal speed." };
const celerity = power({ added: [quickness] });
const meld = power({ key: "Earth Meld", name: "Earth Meld", origin: "Protean 3", form: true, page: "p. 155", notes: ["Can't act or use powers."], added: [earthControl] });
const tap = () => {};

describe("notes another power adds to a switch (#601)", () => {
  it("shows them with the switch, under the power's name and page", () => {
    render(<PowersList powers={[celerity, meld]} tap={tap} />);
    expect(within(screen.getByRole("list", { name: "Powers" })).getByText("Quickness (p. 214): An extra round of actions, taken in the third Celerity round.")).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Forms" })).getByText("Earth Control (p. 221): Move underground at your normal speed.")).toBeTruthy();
  });

  it("shows them in the banner while the switch is on, and not while it is off", () => {
    const { rerender } = render(<PowersBanner powers={[celerity, meld]} tap={tap} />);
    expect(screen.queryByText(/Quickness/)).toBeNull();
    rerender(<PowersBanner powers={[{ ...celerity, on: true }, { ...meld, on: true }]} tap={tap} />);
    const banner = screen.getByRole("region", { name: "Switched on now" });
    expect(within(banner).getByText("Quickness (p. 214): An extra round of actions, taken in the third Celerity round.")).toBeTruthy();
    expect(within(banner).getByText("Earth Control (p. 221): Move underground at your normal speed.")).toBeTruthy();
  });

  it("adds nothing to a switch without them", () => {
    render(<PowersList powers={[power({})]} tap={tap} />);
    expect(screen.queryByText(/Quickness/)).toBeNull();
  });
});

describe("an Off button for each power in the banner (#697)", () => {
  const might = power({ key: "Might", name: "Might", origin: "Potence 1", notes: [], on: true });
  const flesh = power({ key: "Flesh of Marble", name: "Protean: Flesh of Marble", origin: "Protean 4", notes: [], on: true, picked: ["Rugged", "Hardened"] });

  it("gives each power on its own Off button, which switches only that power off", () => {
    const taps = vi.fn();
    render(<PowersBanner powers={[{ ...celerity, on: true }, might, { ...meld, on: true }]} tap={taps} />);
    const banner = screen.getByRole("region", { name: "Switched on now" });
    const rows = within(within(banner).getByRole("list", { name: "Powers on" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]!.textContent).toContain("On: Celerity");
    expect(rows[0]!.textContent).toContain("For the turn: 1 Blood activates every Celerity power you have.");
    fireEvent.click(within(banner).getByRole("button", { name: "Switch Might off" }));
    expect(taps).toHaveBeenCalledTimes(1);
    expect(taps).toHaveBeenCalledWith({ kind: "change", tracker: switchKey("Might"), amount: -1 });
    // The form keeps its own way back.
    expect(within(banner).getByRole("button", { name: "Turn back" })).toBeTruthy();
  });

  it("names a power's picks on its Off button", () => {
    render(<PowersBanner powers={[flesh]} tap={tap} />);
    expect(screen.getByRole("button", { name: "Switch Protean: Flesh of Marble (Rugged, Hardened) off" })).toBeTruthy();
  });

  it("keeps to names and Off buttons with more than three on", () => {
    const many = ["A", "B", "C", "D"].map((n) => power({ key: n, name: n, on: true, added: [quickness] }));
    render(<PowersBanner powers={many} tap={tap} />);
    expect(screen.getAllByRole("button", { name: /^Switch . off$/ })).toHaveLength(4);
    expect(screen.queryByText(/Quickness/)).toBeNull();
    expect(screen.queryByText(/For the turn/)).toBeNull();
  });
});

describe("a power kept until undone (#822)", () => {
  const heart = power({ key: "Heart removed", name: "Heart of Darkness: heart removed", kept: true, notes: [] });
  const visage = power({ key: "Alien beauty", name: "Malleable Visage: alien beauty", kept: true, normal_form_only: true, notes: [], on: true });
  const wolf = power({ key: "fight form", name: "fight form", form: true, notes: [], on: true });

  it("says it is kept through Reset, and paused in a form when it changes the normal form only", () => {
    render(<PowersList powers={[heart, visage, wolf]} tap={vi.fn()} />);
    expect(screen.getByText("Lasts until undone: kept through Reset until you turn it off.")).toBeTruthy();
    expect(screen.getByText("Kept through Reset until you turn it off.")).toBeTruthy();
    expect(screen.getByText("Paused while you're in a form: it changes your normal form only.")).toBeTruthy();
  });

  it("is shown as kept in the banner", () => {
    render(<PowersBanner powers={[{ ...heart, on: true }]} tap={vi.fn()} />);
    const banner = screen.getByRole("region", { name: "Switched on now" });
    expect(banner.textContent).toContain("Kept: Heart of Darkness: heart removed");
  });
});
