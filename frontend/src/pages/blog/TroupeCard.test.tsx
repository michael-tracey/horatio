import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { BlogTroupeCardOut } from "../../api/types";
import { TroupeCard } from "./TroupeCard";

afterEach(cleanup);

const LORDS: BlogTroupeCardOut = { id: "lords", name: "Lords of the Night", abbreviation: "LotN", portrait: "/api/troupes/lords/portraits/p9", description: "A Camarilla game in Leeds.\nSecond Saturdays." };

function show(troupe: BlogTroupeCardOut) {
  render(
    <MemoryRouter>
      <TroupeCard troupe={troupe} />
    </MemoryRouter>,
  );
  return screen.getByRole("region", { name: `About ${troupe.name}` });
}

describe("an article's troupe card (#1160)", () => {
  it("shows the troupe's portrait, name linked to its profile, pill and description", () => {
    const card = show(LORDS);
    expect(screen.getByRole("link", { name: "Lords of the Night" }).getAttribute("href")).toBe("/t/lords");
    expect(screen.getByTitle("Lords of the Night").textContent).toBe("LotNLords of the Night");
    expect(card.querySelector("img")?.getAttribute("src")).toBe("/api/troupes/lords/portraits/p9/128.webp");
    expect(screen.getByText(/A Camarilla game in Leeds\./).className).toContain("line-clamp-4");
  });

  it("leaves out the pill when it goes by its name, and the description when it has none, with initials for no portrait", () => {
    const card = show({ ...LORDS, abbreviation: "Lords of the Night", portrait: null, description: "  " });
    expect(screen.queryByTitle("Lords of the Night")).toBeNull();
    expect(card.querySelector("img")).toBeNull();
    expect(card.textContent).toBe("LNLords of the NightTroupe");
  });
});
