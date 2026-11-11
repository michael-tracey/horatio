import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TraitOut } from "../../../api/types";
import { PointsList } from "./DotGrid";

afterEach(cleanup);

const flaw = (name: string, points: number) => ({ category: "flaws", name, fixed_rating: points, description: null }) as unknown as TraitOut;
const FLAWS = [flaw("Hunted", 4), flaw("Fragile Bones", 4), flaw("Dark Secret", 1)];

describe("PointsList", () => {
  it("lets flaws go past their budget, saying they give no more XP", () => {
    const onChange = vi.fn();
    render(<PointsList title="Flaws" traits={FLAWS} budget={7} pastBudget picks={{ Hunted: 4, "Fragile Bones": 4 }} onChange={onChange} />);

    expect(screen.getByText("8 points, 7 XP paid out")).toBeTruthy();
    expect(screen.getByText("Flaws past 7 points need the Storyteller's OK, and give no more XP (p. 85).")).toBeTruthy();
    const darkSecret = screen.getByRole("checkbox", { name: /Dark Secret/ }) as HTMLInputElement;
    expect(darkSecret.disabled).toBe(false);
    fireEvent.click(darkSecret);
    expect(onChange).toHaveBeenCalledWith({ Hunted: 4, "Fragile Bones": 4, "Dark Secret": 1 });
  });

  it("keeps merits to their budget", () => {
    const merits = [flaw("Rugged", 3), flaw("Iron Will", 3), flaw("Additional Common Discipline", 4)].map((t) => ({ ...t, category: "merits" }));
    render(<PointsList title="Merits" traits={merits} budget={7} picks={{ Rugged: 3, "Iron Will": 3 }} onChange={vi.fn()} />);

    expect(screen.getByText("6 of 7 points")).toBeTruthy();
    expect((screen.getByRole("checkbox", { name: /Additional Common Discipline/ }) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByText(/Storyteller's OK/)).toBeNull();
  });
});
