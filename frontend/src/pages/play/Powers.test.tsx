import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { PowerSwitch } from "../../api/types";
import { PowersBanner, PowersList } from "./Powers";

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
  turned_on: 0,
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
