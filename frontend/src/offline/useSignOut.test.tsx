import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { createMemoryRouter, Outlet, useLocation } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Me } from "../api/types";
import { LeaveGuard } from "../components/LeaveGuard";
import { useLeaveWarning, useMe } from "../hooks";
import { RequireSignIn } from "../RequireSignIn";
import { useSignOut } from "./Offline";

// What signing out clears on the device is store.test.ts's; here, only who is signed in.
vi.mock("./push", () => ({ stopPushHere: async () => {} }));
vi.mock("./store", async (real) => ({
  ...(await real<typeof import("./store")>()),
  forget: async (client: QueryClient) => client.setQueryData(["me"], null),
}));

// jsdom has no modal dialogs.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const agnes = { id: "u1", handle: "agnes", display_name: "Agnes" } as Me;

/** As the layout does: Sign out above the page, round every page the guard. */
function Shell() {
  const me = useMe();
  const signOut = useSignOut();
  const { pathname, search } = useLocation();
  if (me.isPending) return <p>Opening</p>;
  return (
    <>
      <button onClick={signOut.signOut}>Sign out</button>
      <p data-testid="where">{pathname + search}</p>
      <Outlet />
      <LeaveGuard />
    </>
  );
}

function Bio() {
  const [bio, setBio] = useState("");
  useLeaveWarning(bio !== "", { inApp: true });
  return <input aria-label="Bio" value={bio} onChange={(e) => setBio(e.target.value)} />;
}

function setup(at: string) {
  vi.spyOn(api, "GET").mockImplementation((async () => ({ data: agnes, response: new Response(null, { status: 200 }) })) as never);
  const loggedOut = vi.spyOn(api, "POST").mockImplementation((async () => ({ data: null, response: new Response(null, { status: 204 }) })) as never);
  const router = createMemoryRouter(
    [
      {
        element: <Shell />,
        children: [
          { index: true, element: <p>The landing page</p> },
          { path: "/sign-in", element: <p>Sign-in form</p> },
          {
            element: <RequireSignIn />,
            children: [
              { path: "/characters", element: <p>Your characters</p> },
              { path: "/account", element: <Bio /> },
            ],
          },
        ],
      },
    ],
    { initialEntries: [at] },
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, loggedOut };
}

const signOut = () => act(async () => fireEvent.click(screen.getByRole("button", { name: "Sign out" })));

describe("signing out", () => {
  it("goes to the landing page, not to sign in (#1180)", async () => {
    const { router, loggedOut } = setup("/characters");
    await screen.findByText("Your characters");
    await signOut();
    expect(loggedOut).toHaveBeenCalledWith("/api/auth/logout");
    expect(await screen.findByText("The landing page")).toBeTruthy();
    expect(screen.getByTestId("where").textContent).toBe("/");
    expect(router.state.location.pathname).toBe("/");
    expect(screen.queryByText("Sign-in form")).toBeNull();
  });

  it("goes there from a form with changes not saved, without asking to leave it", async () => {
    setup("/account");
    fireEvent.change(await screen.findByLabelText("Bio"), { target: { value: "Playing since the old days." } });
    await signOut();
    expect(await screen.findByText("The landing page")).toBeTruthy();
    expect(screen.queryByText(/Leave anyway/)).toBeNull();
  });
});
