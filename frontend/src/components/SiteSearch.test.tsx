import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { SiteSearch } from "./SiteSearch";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const HERE = "01a1f972-9b2f-78ce-ad90-4eb19b104d1c";
const THERE = "01a1f972-0000-78ce-ad90-4eb19b104d1c";

function Where() {
  return <p data-testid="where">{useLocation().pathname + useLocation().search}</p>;
}

function setup() {
  const asked = vi.spyOn(api, "GET").mockResolvedValue({
    data: {
      groups: [
        {
          kind: "characters",
          label: "Characters",
          more: false,
          hits: [
            { id: "c1", title: "Ravenna", detail: "", to: "/characters/c1", troupe_id: HERE, troupe: "Lords of the Night" },
            { id: "c2", title: "Raven Two", detail: "NPC", to: "/characters/c2", troupe_id: THERE, troupe: "Other Court" },
          ],
        },
        {
          kind: "boons",
          label: "Boons",
          more: true,
          hits: [{ id: "b1", title: "Ravenna owes Corvin a minor boon", detail: "Passage", to: `/troupes/${HERE}/boons?boon=b1`, troupe_id: HERE, troupe: "Lords of the Night" }],
        },
      ],
    },
    response: new Response(null, { status: 200 }),
  } as never);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[`/troupes/${HERE}/boons`]}>
        <SiteSearch />
        <Routes>
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { asked };
}

// jsdom has no showModal: open and close by the attribute, as a browser would.
HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
};

describe("SiteSearch", () => {
  it("opens from its button and from / on the page", () => {
    setup();
    expect(screen.queryByRole("searchbox")).toBeNull();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(screen.getByRole("searchbox", { name: "Search for" })).toBeTruthy();
  });

  it("asks once the typing stops, for the troupe the page is of, and shows the hits by kind", async () => {
    const { asked } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Search everything" }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "raven" } });

    expect(await screen.findByRole("heading", { name: "Characters" })).toBeTruthy();
    expect(asked).toHaveBeenCalledWith("/api/search", { params: { query: { q: "raven", troupe_id: HERE } } });
    expect(screen.getByRole("heading", { name: "Boons" })).toBeTruthy();
    // Another troupe's says which; the current troupe's needn't.
    expect(screen.getByRole("link", { name: /Raven Two/ }).textContent).toContain("Other Court");
    expect(screen.getByRole("link", { name: /^Ravenna$/ }).textContent).not.toContain("Lords of the Night");
    expect(screen.getByText(/More than these/)).toBeTruthy();
  });

  it("opens the first hit on Enter, and a hit on choosing it, closing", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Search everything" }));
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "raven" } });
    await screen.findByRole("heading", { name: "Characters" });

    fireEvent.keyDown(box, { key: "Enter" });

    expect(screen.getByTestId("where").textContent).toBe("/characters/c1");
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  it("goes down through the hits with the arrow keys", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Search everything" }));
    const box = screen.getByRole("searchbox");
    fireEvent.change(box, { target: { value: "raven" } });
    await screen.findByRole("heading", { name: "Characters" });

    box.focus();
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("Ravenna");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Ravenna owes Corvin");
    fireEvent.click(document.activeElement!);
    expect(screen.getByTestId("where").textContent).toBe(`/troupes/${HERE}/boons?boon=b1`);
  });
});
