import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { BookTraitOut, BookTraitsOut, CatalogueOut, CategoryOut, TraitOut } from "../../api/types";
import { BookTraitsSection, keepInPlace } from "./BookTraitsSection";

afterEach(cleanup);

const category = (key: string, name: string) => ({ key, name, derived: false }) as CategoryOut;
const trait = (name: string, more: Partial<TraitOut> = {}) =>
  ({ name, category: "merits", description: `${name}, by the book.`, page_reference: null, ...more }) as TraitOut;
const change = (name: string, more: Partial<BookTraitOut> = {}): BookTraitOut => ({
  splat: "vampire",
  splat_label: "Vampire",
  category: "merits",
  category_name: "Merits",
  name,
  page: null,
  banned: true,
  ban_reason: "",
  wording: "",
  wording_mode: "added",
  kind: null,
  book_kind: null,
  ...more,
});

const CHANGES = [change("Lucky"), change("Iron Will", { banned: false, wording: "Ours." })];

/** The page, with the catalogue and the troupe's changes already fetched and the API never asked. */
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  const catalogue = {
    categories: [category("merits", "Merits")],
    traits: [
      trait("Iron Will", { changed: { banned: false, ban_reason: "", wording: "Ours.", wording_mode: "added" } as TraitOut["changed"] }),
      trait("Lucky", { changed: { banned: true, ban_reason: "", wording: "", wording_mode: "added" } as TraitOut["changed"] }),
      trait("Luminous Aura"),
    ],
  } as unknown as CatalogueOut;
  client.setQueryData(["catalogue", "vampire", "t1"], catalogue);
  client.setQueryData(["book-traits", "t1"], { changes: CHANGES, holders: [], kinds: {} } as unknown as BookTraitsOut);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <BookTraitsSection troupeId="t1" canEdit />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const changedRow = (name: string) => screen.getAllByRole("listitem").find((li) => li.firstElementChild?.textContent?.startsWith(name))!;

describe("the Book traits page's panel (#648)", () => {
  it("opens under the row that opened it, with the focus in it, and the row's button closes it again", () => {
    show();
    const open = screen.getByRole("button", { name: "Open Lucky" });
    fireEvent.click(open);

    const panel = within(changedRow("Lucky")).getByRole("region", { name: "Lucky" });
    expect(panel).toBeTruthy();
    expect(within(changedRow("Iron Will")).queryByRole("region", { name: "Iron Will" })).toBeNull();
    expect(document.activeElement).toBe(within(panel).getByLabelText(/Banned in this troupe/));
    expect(open.textContent).toBe("Close");
    expect(open.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Close Lucky" }));
    expect(screen.queryByRole("region", { name: "Lucky" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Open Lucky" }));
  });

  it("shows one panel at a time, a search's under the trait found", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Open Lucky" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search book traits" }), { target: { value: "lumin" } });
    const found = screen.getByRole("list", { name: "Book traits found" });
    fireEvent.click(within(found).getByRole("button", { name: /^Luminous Aura/ }));

    const panels = screen.getAllByRole("region", { name: /^(Lucky|Iron Will|Luminous Aura)$/ });
    expect(panels).toHaveLength(1);
    expect(panels[0]!.querySelector("h3")?.textContent).toBe("Luminous Aura");
    expect(within(within(found).getByRole("listitem")).getByRole("region", { name: "Luminous Aura" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Lucky" }).getAttribute("aria-expanded")).toBe("false");

    // Its Close puts the focus back on the trait found.
    fireEvent.click(within(screen.getByRole("region", { name: "Luminous Aura" })).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("region", { name: "Luminous Aura" })).toBeNull();
    expect(document.activeElement).toBe(within(found).getByRole("button", { name: /^Luminous Aura/ }));
  });
});

describe("keepInPlace", () => {
  const same = (a: BookTraitOut, b: BookTraitOut) => a.name === b.name;
  const gone = (c: BookTraitOut) => ({ ...c, banned: false });
  const [lucky, iron] = CHANGES as [BookTraitOut, BookTraitOut];

  it("keeps the change whose panel is open in its place, though saving took it from the list", () => {
    const kept = keepInPlace([iron], { row: lucky, at: 0 }, same, gone);
    expect(kept.map((c) => c.name)).toEqual(["Lucky", "Iron Will"]);
    expect(kept[0]!.banned).toBe(false);
  });

  it("keeps a trait found where it was, though saving moved it first", () => {
    expect(keepInPlace([iron, lucky], { row: iron, at: 1 }, same).map((c) => c.name)).toEqual(["Lucky", "Iron Will"]);
  });

  it("lets a row go with no way to bring it back, and leaves the list alone with no panel open", () => {
    expect(keepInPlace([iron], { row: lucky, at: 0 }, same)).toEqual([iron]);
    expect(keepInPlace(CHANGES, null, same)).toBe(CHANGES);
  });
});
