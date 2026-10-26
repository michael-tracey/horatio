import { describe, expect, it } from "vitest";
import type { PoolModifier, PowerSwitch } from "../../api/types";
import { inUse } from "./SwitchesDrawer";

const power = (name: string, on: boolean) => ({ name, on }) as PowerSwitch;
const modifier = (label: string, amount: number, on: boolean) => ({ label, amount, on }) as PoolModifier;

describe("inUse", () => {
  it("says so when nothing is on", () => {
    expect(inUse([power("Celerity", false)], [modifier("Fame", 2, false)])).toBe("Nothing in use");
    expect(inUse([], [])).toBe("Nothing in use");
  });

  it("lists the powers on, then the modifiers on with their amounts", () => {
    const powers = [power("Shape of the Beast: fight form", true), power("Celerity", false), power("Feral Claws", true)];
    const modifiers = [modifier("Ambush", 2, true), modifier("Fame", 2, false), modifier("Wounded", -1, true)];
    expect(inUse(powers, modifiers)).toBe("In use: Shape of the Beast: fight form, Feral Claws, +2 Ambush, −1 Wounded");
  });
});
