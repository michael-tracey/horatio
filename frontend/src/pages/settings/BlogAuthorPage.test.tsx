import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { MyAuthor } from "../../api/types";
import { BlogAuthorPage } from "./BlogAuthorPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const NEW: MyAuthor = {
  saved: false,
  display_name: "Sam Ashdown",
  handle: "sam",
  bio: "",
  links: [],
  picture: null,
  picture_crop: null,
  public: false,
  pictures_available: true,
};

/** The tab, with the server answering `author`, then what was last saved. */
function show(author: MyAuthor = NEW) {
  let kept = author;
  vi.spyOn(api, "GET").mockImplementation((async () => ({ data: kept, response: new Response(null, { status: 200 }) })) as never);
  const put = vi.spyOn(api, "PUT").mockImplementation((async (_path: string, { body }: { body: Partial<MyAuthor> }) => {
    kept = { ...kept, ...body, handle: body.handle!.replace(/^@/, ""), saved: true, public: true };
    return { data: kept, response: new Response(null, { status: 200 }) };
  }) as never);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <BlogAuthorPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return put;
}

describe("Account › Blog author", () => {
  it("previews the card live as it is typed, and saves what it shows", async () => {
    const put = show();
    const preview = await screen.findByRole("region", { name: "About Sam Ashdown" });
    expect(within(preview).getByText("@sam")).toBeTruthy();
    expect(screen.getByText(/you have no author profile until you save/)).toBeTruthy();
    // A picture waits for the profile to be saved.
    expect(screen.getByText("Save your author profile first, then add a picture.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Sam the Storyteller" } });
    fireEvent.change(screen.getByLabelText("Author handle"), { target: { value: "@sam_writes" } });
    fireEvent.change(screen.getByLabelText("Bio"), { target: { value: "Runs *Lords of the Night*." } });
    const card = screen.getByRole("region", { name: "About Sam the Storyteller" });
    expect(within(card).getByText("@sam_writes")).toBeTruthy();
    expect(within(card).getByText("Lords of the Night").tagName).toBe("EM");
    expect(screen.getByText(/Your page's address: \/blog\/authors\/sam_writes/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("link", { name: "See your author page" })).toBeTruthy();
    expect(put).toHaveBeenCalledWith("/api/blog/author", {
      body: { display_name: "Sam the Storyteller", handle: "@sam_writes", bio: "Runs *Lords of the Night*.", links: [] },
    });
  });

  it("says when no one else can see the page yet", async () => {
    show({ ...NEW, saved: true, public: false });
    expect(await screen.findByText(/Only you can see your author page for now/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose a picture" })).toBeTruthy();
  });
});
