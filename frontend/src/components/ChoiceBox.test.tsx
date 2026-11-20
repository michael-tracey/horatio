import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TraitOut } from "../api/types";
import { ChoiceBox, oneLine, type BoxChoice } from "./ChoiceBox";

afterEach(cleanup);

function client() {
  const found = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  found.setQueryData(["me"], null);
  found.setQueryData(["power-notes", "vampire"], {
    disciplines: [{ name: "Auspex", pool: "Mental + Investigation", versus: "Mental + Willpower" }],
    powers: [{ discipline: "Auspex", level: 1, name: "Heightened Senses", note: "Sharper senses." }],
  });
  return found;
}

const auspex: TraitOut = { category: "disciplines", name: "Auspex", description: "Heightened senses and psychic insight.", page_reference: "128" };
const dementation: TraitOut = { category: "disciplines", name: "Dementation", description: "Madness, passed on.", page_reference: "142" };
const choices: BoxChoice[] = [
  { value: "disciplines/Auspex", label: "Auspex", trait: auspex, mark: "in-clan" },
  { value: "disciplines/Dementation", label: "Dementation", trait: dementation, note: "A Neonate can't learn it without a teacher." },
];

function box(onChoose = vi.fn(), value?: string, offered = choices) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={client()}>
        <ChoiceBox label="Search Disciplines" placeholder="Search to add…" value={value} choices={offered} onChoose={onChoose} splat="vampire" />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return screen.getByRole("combobox", { name: "Search Disciplines" });
}

describe("ChoiceBox", () => {
  it("lists each choice with what it does in a line, and narrows the list as one types", () => {
    const input = box();
    fireEvent.focus(input);
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("option", { name: "Auspex" }).textContent).toContain("Heightened senses and psychic insight.");
    expect(screen.getByRole("option", { name: "Auspex" }).textContent).toContain("in-clan");
    fireEvent.change(input, { target: { value: "demen" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });

  it("shows the highlighted one's detail, and chooses it with Enter", () => {
    const onChoose = vi.fn();
    const input = box(onChoose);
    fireEvent.focus(input);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[0]!.id);
    expect(screen.getByText("Dots 1 to 5 give:")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChoose).toHaveBeenCalledWith("disciplines/Auspex");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("greys one the character can't usually take, saying why, and lets staff choose it", () => {
    const onChoose = vi.fn();
    const input = box(onChoose);
    fireEvent.focus(input);
    const option = screen.getByRole("option", { name: "Dementation" });
    expect(option.getAttribute("aria-disabled")).toBeNull();
    expect(document.getElementById(option.getAttribute("aria-describedby")!)?.textContent).toBe("A Neonate can't learn it without a teacher.");
    fireEvent.click(screen.getByRole("button", { name: "About Dementation" }));
    expect(screen.getByText(/Staff can give it all the same\./)).toBeTruthy();
    expect(onChoose).not.toHaveBeenCalled();
    fireEvent.click(option);
    expect(onChoose).toHaveBeenCalledWith("disciplines/Dementation");
  });

  it("greys one the rules refuse a player, which can't be chosen, and offers what can be done instead", () => {
    const onChoose = vi.fn();
    const ask = vi.fn();
    const refused: BoxChoice[] = [
      choices[0]!,
      { ...choices[1]!, disabled: true, note: "Dementation is out of clan.", action: { label: "Ask staff", run: ask } },
    ];
    const input = box(onChoose, undefined, refused);
    fireEvent.focus(input);
    const option = screen.getByRole("option", { name: "Dementation" });
    expect(option.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(option);
    expect(onChoose).not.toHaveBeenCalled();
    // Its detail still opens, and Enter on it asks staff.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(option.id);
    expect(screen.queryByText(/Staff can give it all the same/)).toBeNull();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(ask).toHaveBeenCalled();
    expect(onChoose).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("offers a pick made elsewhere by where it is, typing finding it by the trait's name", () => {
    const onChoose = vi.fn();
    const moving: BoxChoice[] = [{ value: "move:Auspex", label: "Auspex: Aura", name: "Auspex", at: 3, trait: auspex }, choices[1]!];
    const input = box(onChoose, undefined, moving);
    fireEvent.change(input, { target: { value: "ausp" } });
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("aria-label"))).toEqual(["Auspex: Aura (at 3)"]);
    // The one choice left that can be made is made with Enter.
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChoose).toHaveBeenCalledWith("move:Auspex");
  });

  it("shows the choice made, highlighted when the list opens", () => {
    const input = box(vi.fn(), "Auspex") as HTMLInputElement;
    expect(input.value).toBe("Auspex");
    fireEvent.focus(input);
    expect(screen.getByRole("option", { name: "Auspex" }).getAttribute("aria-selected")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getByRole("option", { name: "Auspex" }).id);
  });

  it("says what a clan highlighted brings: its in-clan disciplines and its weakness, with the weakness's page", () => {
    const brujah: TraitOut = { category: "clan", name: "Brujah", in_clan: ["Celerity", "Potence", "Presence"], weakness: "Quick to rage.", weakness_page: "45" };
    const input = box(vi.fn(), undefined, [{ value: "Brujah", label: "Brujah", trait: brujah }]);
    fireEvent.focus(input);
    expect(screen.getByRole("option", { name: "Brujah" }).textContent).toContain("In-clan: Celerity, Potence, Presence");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    const about = screen.getByRole("region", { name: "About the highlighted choice" });
    expect(about.textContent).toContain("In-clan disciplines: Celerity, Potence, Presence.");
    expect(about.textContent).toContain("Weakness: Quick to rage. (p. 45)");
  });
});

describe("oneLine", () => {
  it("is a clan's in-clan disciplines, else the troupe's summary, else the book's", () => {
    expect(oneLine({ category: "clan", name: "Ventrue", in_clan: ["Dominate", "Fortitude", "Presence"] })).toBe("In-clan: Dominate, Fortitude, Presence");
    expect(oneLine(auspex)).toBe("Heightened senses and psychic insight.");
    expect(oneLine(undefined)).toBeNull();
  });
});
