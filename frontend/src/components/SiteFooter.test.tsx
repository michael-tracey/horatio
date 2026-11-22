import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { SiteFooter } from "./Layout";

afterEach(cleanup);

function links(signedIn: boolean) {
  render(
    <MemoryRouter>
      <SiteFooter width="max-w-5xl" signedIn={signedIn} />
    </MemoryRouter>,
  );
  return screen.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);
}

describe("SiteFooter", () => {
  it("signed out, on the public pages, links to About, the blog and Help (#1162)", () => {
    expect(links(false)).toEqual([
      ["About Horatio", "/about"],
      ["Blog", "/blog"],
      ["Help", "/help"],
    ]);
  });

  it("signed in, links only to About, as before", () => {
    expect(links(true)).toEqual([["About Horatio", "/about"]]);
  });
});
