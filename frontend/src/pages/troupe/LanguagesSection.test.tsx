import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LanguagesOut } from "../../api/types";
import { LanguagesForm } from "./LanguagesSection";

afterEach(cleanup);

const book: LanguagesOut = {
  mode: "book",
  custom: [],
  natural_doubles: true,
  table: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
  accelerated: [1, 2, 4, 8, 16, 24, 32],
  max_rating: 10,
  text: "one per dot of Linguistics (the book's); Natural Linguist doubles it",
  book_text: "One per dot of Linguistics; Natural Linguist doubles it (pp. 94, 252)",
  over: [],
};

function form(data: LanguagesOut, canEdit = true) {
  const onSave = vi.fn();
  render(
    <MemoryRouter>
      <LanguagesForm data={data} canEdit={canEdit} onSave={onSave} />
    </MemoryRouter>,
  );
  return onSave;
}

const languagesRow = () => within(screen.getByRole("row", { name: /^Languages/ })).getAllByRole("cell").map((c) => c.textContent);

describe("LanguagesForm", () => {
  it("offers the accelerated chart as a preset, doubled for Natural Linguist", () => {
    const onSave = form(book);
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText(/Accelerated chart/));

    expect(languagesRow()).toEqual(["1", "2", "4", "8", "16", "24", "32", "32", "32", "32"]);
    expect(within(screen.getByRole("row", { name: /With Natural Linguist/ })).getAllByRole("cell")[4]!.textContent).toBe("32");
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledWith({ mode: "accelerated", custom: null, natural_doubles: true });
  });

  it("edits the troupe's own chart, one figure per rating, and refuses one that goes down", () => {
    const onSave = form(book);

    fireEvent.click(screen.getByLabelText(/Custom/));
    const inputs = screen.getAllByLabelText(/Languages at Linguistics \d+/) as HTMLInputElement[];
    expect(inputs).toHaveLength(10);
    expect(inputs.map((i) => i.value).slice(0, 3)).toEqual(["1", "2", "3"]);
    fireEvent.change(screen.getByLabelText("Languages at Linguistics 2"), { target: { value: "0" } });

    expect(screen.getByText("Linguistics 2 cannot give fewer languages than Linguistics 1.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Languages at Linguistics 2"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Languages at Linguistics 3"), { target: { value: "4" } });
    fireEvent.click(screen.getByLabelText(/Natural Linguist doubles it/));
    expect(screen.queryByRole("row", { name: /With Natural Linguist/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(onSave).toHaveBeenCalledWith({ mode: "custom", custom: [1, 3, 4, 4, 5, 6, 7, 8, 9, 10], natural_doubles: false });
  });

  it("shows staff who cannot change it the chart in use, and who holds more than it allows", () => {
    form({ ...book, mode: "accelerated", table: [1, 2, 4, 8, 16, 24, 32, 32, 32, 32], text: "1, 2, 4 … (the accelerated chart)", over: [{ character_id: "a", name: "Agnes", held: 5, allowed: 4 }] }, false);

    expect(screen.queryByRole("radio")).toBeNull();
    expect(languagesRow()[4]).toBe("16");
    expect(screen.getByRole("link", { name: "Agnes" }).getAttribute("href")).toBe("/characters/a");
    expect(screen.getByText("5 of 4 languages")).toBeTruthy();
  });
});
