import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router";
import { api } from "./api/client";
import type { Me } from "./api/types";
import { useMe } from "./hooks";
import { RequireSignIn } from "./RequireSignIn";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const agnes = { id: "u1", handle: "agnes", display_name: "Agnes" } as Me;

/** What `/api/auth/me` answers, one status at a time; anything else the page asks is a 404. */
function answers(...statuses: number[]) {
  const asked: number[] = [];
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path !== "/api/auth/me") return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
    const status = statuses[Math.min(asked.length, statuses.length - 1)]!;
    asked.push(status);
    if (status === 200) return { data: agnes, response: new Response(null, { status }) };
    return { error: status === 401 ? { detail: "Not signed in" } : {}, response: new Response(null, { status }) };
  }) as never);
  return asked;
}

function SignInForm() {
  const { search } = useLocation();
  return <p>Sign-in form {search}</p>;
}

/** As the layout does: its loading screen in place of the page until who is signed in is known. */
function Shell() {
  return useMe().isPending ? <p>Opening</p> : <Outlet />;
}

function show(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/characters?tab=mine"]}>
        <Routes>
          <Route path="/sign-in" element={<SignInForm />} />
          <Route element={<Shell />}>
            <Route element={<RequireSignIn />}>
              <Route path="/characters" element={<p>Your characters</p>} />
            </Route>
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the pages for someone signed in", () => {
  it("say a failed session check on the page asked for, with Try again, not the sign-in form", async () => {
    answers(500);
    show();
    expect(await screen.findByText("Couldn't check that you're signed in.")).not.toBeNull();
    expect(screen.getByRole("alert").textContent).toBe("Something went wrong (500).");
    expect(screen.getByRole("button", { name: "Try again" })).not.toBeNull();
    expect(screen.queryByText(/Sign-in form/)).toBeNull();
  });

  it("ask once, not again each time the page opens on the failure", async () => {
    const asked = answers(500);
    show();
    await screen.findByRole("button", { name: "Try again" });
    await new Promise((r) => setTimeout(r, 50));
    expect(asked).toEqual([500]);
  });

  it("send someone with no session to sign in, and on to where they were going", async () => {
    answers(401);
    show();
    expect((await screen.findByText(/Sign-in form/)).textContent).toBe(`Sign-in form ?next=${encodeURIComponent("/characters?tab=mine")}`);
  });

  it("open once Try again finds the person signed in", async () => {
    const asked = answers(503, 200);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Your characters")).not.toBeNull();
    expect(asked).toEqual([503, 200]);
  });

  it("send to sign in when Try again finds no session", async () => {
    answers(500, 401);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Sign-in form/)).not.toBeNull();
  });

  it("stay open when a check fails after the person is known, as from what is kept on the device", async () => {
    const asked = answers(500);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // Restored, and stale at once, so it is asked afresh.
    client.setQueryData(["me"], agnes, { updatedAt: 0 });
    show(client);
    expect(await screen.findByText("Your characters")).not.toBeNull();
    await vi.waitFor(() => expect(asked).toEqual([500]));
    expect(screen.getByText("Your characters")).not.toBeNull();
    expect(screen.queryByText("Couldn't check that you're signed in.")).toBeNull();
  });
});
