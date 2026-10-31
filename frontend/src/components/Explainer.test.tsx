import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EmptyState, FilterBar, showFilters } from "./EmptyState";
import { Explainer, explainerOpen, rememberExplainer } from "./Explainer";

afterEach(cleanup);
beforeEach(() => localStorage.clear());

const details = () => screen.getByText("How costs work").closest("details")!;

describe("Explainer", () => {
  it("opens the first time it is seen, and is closed the next", () => {
    render(<Explainer id="costs" title="How costs work">The most specific price wins.</Explainer>);
    expect(details().open).toBe(true);
    cleanup();
    render(<Explainer id="costs" title="How costs work">The most specific price wins.</Explainer>);
    expect(details().open).toBe(false);
  });

  it("stays as it was left by hand", () => {
    rememberExplainer("costs", "seen");
    render(<Explainer id="costs" title="How costs work">The most specific price wins.</Explainer>);
    fireEvent.click(screen.getByText("How costs work"));
    expect(details().open).toBe(true);
    cleanup();
    render(<Explainer id="costs" title="How costs work">The most specific price wins.</Explainer>);
    expect(details().open).toBe(true);
    fireEvent.click(screen.getByText("How costs work"));
    expect(details().open).toBe(false);
    expect(explainerOpen("costs")).toBe(false);
  });

  it("keeps each explainer apart, and opens when nothing can be kept", () => {
    rememberExplainer("costs", "seen");
    expect(explainerOpen("costs")).toBe(false);
    expect(explainerOpen("status")).toBe(true);
    const blocked = {
      getItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(explainerOpen("costs", blocked)).toBe(true);
  });
});

describe("Empty lists", () => {
  it("say what to do next, with an action if given", () => {
    render(
      <EmptyState title="No locations yet." action={<button>Add a location</button>}>
        Start with Add a location.
      </EmptyState>,
    );
    expect(screen.getByText("No locations yet.")).toBeTruthy();
    expect(screen.getByText("Start with Add a location.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add a location" })).toBeTruthy();
  });

  it("show no filters until there is something to filter", () => {
    expect(showFilters(0, false)).toBe(false);
    expect(showFilters(undefined, false)).toBe(false);
    expect(showFilters(3, false)).toBe(true);
    // A filter that finds nothing keeps them, to undo it.
    expect(showFilters(0, true)).toBe(true);
    render(
      <FilterBar count={0} filtering={false}>
        <label>
          Type <select />
        </label>
      </FilterBar>,
    );
    expect(screen.queryByLabelText("Type")).toBeNull();
  });
});
