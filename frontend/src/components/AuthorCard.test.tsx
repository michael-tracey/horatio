import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { AuthorCard as Author } from "../api/types";
import { AuthorCard, authorPath } from "./AuthorCard";

afterEach(cleanup);

const SAM: Author = {
  handle: "sam_writes",
  display_name: "Sam Ashdown",
  bio: "Running **Lords of the Night** since 2019.",
  links: [
    { label: "Bluesky", url: "https://bsky.app/profile/sam" },
    { label: "Sneaky", url: "javascript:alert(1)" },
  ],
  picture: null,
};

function show(author: Author, linked = false) {
  return render(
    <MemoryRouter>
      <AuthorCard author={author} linked={linked} />
    </MemoryRouter>,
  );
}

describe("AuthorCard", () => {
  it("shows the author's name, handle, bio as Markdown, and links that search engines don't follow", () => {
    show(SAM);
    const card = screen.getByRole("region", { name: "About Sam Ashdown" });
    expect(within(card).getByText("Sam Ashdown")).toBeTruthy();
    expect(within(card).getByText("@sam_writes")).toBeTruthy();
    expect(within(card).getByText("Lords of the Night").tagName).toBe("STRONG");
    const link = within(card).getByRole("link", { name: "Bluesky" });
    expect(link.getAttribute("href")).toBe("https://bsky.app/profile/sam");
    expect(link.getAttribute("rel")).toContain("nofollow");
    // Never a link that runs script: only its words.
    expect(within(card).queryByRole("link", { name: "Sneaky" })).toBeNull();
    expect(within(card).getByText("Sneaky")).toBeTruthy();
  });

  it("shows their initials without a picture, and the picture's sizes with one", () => {
    const { container, rerender } = show(SAM);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("SA")).toBeTruthy();
    rerender(
      <MemoryRouter>
        <AuthorCard author={{ ...SAM, picture: "/api/blog/author-pictures/a/p" }} />
      </MemoryRouter>,
    );
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/api/blog/author-pictures/a/p/96.webp");
    expect(img.getAttribute("srcset")).toContain("/api/blog/author-pictures/a/p/256.webp 2x");
  });

  it("links the name to the author's page when asked", () => {
    show({ ...SAM, bio: "", links: [] }, true);
    expect(screen.getByRole("link", { name: "Sam Ashdown" }).getAttribute("href")).toBe("/blog/authors/sam_writes");
    expect(screen.queryByRole("list")).toBeNull();
    expect(authorPath("a b")).toBe("/blog/authors/a%20b");
  });

  it("is their name alone, leading nowhere, while their page is hidden (#1182)", () => {
    show({ handle: null, display_name: "Sam Ashdown", bio: "", links: [], picture: null }, true);
    const card = screen.getByRole("region", { name: "About Sam Ashdown" });
    expect(within(card).getByText("Sam Ashdown")).toBeTruthy();
    expect(within(card).queryByRole("link")).toBeNull();
    expect(within(card).queryByText(/^@/)).toBeNull();
  });
});
