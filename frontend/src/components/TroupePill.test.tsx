import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TroupePill } from "./TroupePill";

afterEach(cleanup);

describe("a troupe's pill (#1153)", () => {
  it("shows what the troupe goes by, with its full name as its tooltip and its words for a screen reader", () => {
    render(<TroupePill name="Court of Ashes" abbreviation="CoA" />);
    const pill = screen.getByTitle("Court of Ashes");
    // Seen: the abbreviation, hidden from a screen reader, which reads the full name instead.
    const seen = pill.querySelector('[aria-hidden="true"]')!;
    expect(seen.textContent).toBe("CoA");
    expect(pill.querySelector(".sr-only")?.textContent).toBe("Court of Ashes");
    expect(pill.textContent).toBe("CoACourt of Ashes");
  });

  it("keeps to one line, cut short, and never more than its share of the row", () => {
    render(<TroupePill name="The Court of the Long Night Over the Harbour" abbreviation="The Court of the Long Night Over the Harbour" />);
    const pill = screen.getByTitle("The Court of the Long Night Over the Harbour");
    expect(pill.className).toContain("shrink-0");
    expect(pill.className).toContain("max-w-[40%]");
    expect(pill.querySelector('[aria-hidden="true"]')!.className).toContain("truncate");
  });
});
