import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { createMemoryRouter, Link, Outlet } from "react-router";
import { RouterProvider } from "react-router/dom";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { useLeaveWarning } from "../hooks";
import { LeaveGuard } from "./LeaveGuard";

// jsdom has no modal dialogs.
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function () {
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(cleanup);

/** A form saved with its button: a bio, and links out of the page. */
function Form({ inApp }: { inApp: boolean }) {
  const [bio, setBio] = useState("");
  useLeaveWarning(bio !== "", { inApp });
  return (
    <>
      <input aria-label="Bio" value={bio} onChange={(e) => setBio(e.target.value)} />
      <Link to="/elsewhere">Elsewhere</Link>
      <Link to="/?tab=links">Same page</Link>
      <Link to="/sign-in">Sign in</Link>
    </>
  );
}

function setup(inApp = true) {
  const router = createMemoryRouter([
    {
      element: (
        <>
          <Outlet />
          <LeaveGuard />
        </>
      ),
      children: [
        { path: "/", element: <Form inApp={inApp} /> },
        { path: "/elsewhere", element: <p>Another page</p> },
        { path: "/sign-in", element: <p>Signing in</p> },
      ],
    },
  ]);
  render(<RouterProvider router={router} />);
  const type = (text: string) => fireEvent.change(screen.getByLabelText("Bio"), { target: { value: text } });
  const click = (name: string) => act(() => fireEvent.click(screen.getByRole("link", { name })));
  return { router, type, click };
}

const asking = () => screen.queryByText("Your changes here aren't saved. Leave anyway? They'll be lost.");

describe("asking before leaving a page with changes not saved", () => {
  it("goes at once when nothing has changed", async () => {
    const { click } = setup();
    await click("Elsewhere");
    expect(await screen.findByText("Another page")).toBeTruthy();
  });

  it("asks first; Cancel stays with the changes, Leave goes on", async () => {
    const { router, type, click } = setup();
    type("Playing since the old days.");
    await click("Elsewhere");
    expect(asking()).not.toBeNull();
    expect(router.state.location.pathname).toBe("/");

    await act(() => fireEvent.click(screen.getByRole("button", { name: "Cancel" })));
    expect(asking()).toBeNull();
    expect(router.state.location.pathname).toBe("/");
    expect((screen.getByLabelText("Bio") as HTMLInputElement).value).toBe("Playing since the old days.");

    await click("Elsewhere");
    await act(() => fireEvent.click(screen.getByRole("button", { name: "Leave" })));
    expect(await screen.findByText("Another page")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/elsewhere");
  });

  it("stops asking once the form goes", async () => {
    const { router, type, click } = setup();
    type("Changed");
    await click("Elsewhere");
    await act(() => fireEvent.click(screen.getByRole("button", { name: "Leave" })));
    await screen.findByText("Another page");
    await act(() => router.navigate("/sign-in"));
    await act(() => router.navigate("/elsewhere"));
    expect(asking()).toBeNull();
    expect(router.state.location.pathname).toBe("/elsewhere");
  });

  it("doesn't ask within the page, or on the way to sign in", async () => {
    const { router, type, click } = setup();
    type("Changed");
    await click("Same page");
    expect(asking()).toBeNull();
    expect(router.state.location.search).toBe("?tab=links");
    await click("Sign in");
    expect(await screen.findByText("Signing in")).toBeTruthy();
  });

  it("leaves a form that saves itself to the browser's question alone", async () => {
    const { type, click } = setup(false);
    type("Changed");
    await click("Elsewhere");
    expect(await screen.findByText("Another page")).toBeTruthy();
    expect(asking()).toBeNull();
  });

  it("asks the browser before the tab closes, either way", () => {
    const { type } = setup(false);
    const closing = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(closing()).toBe(false);
    type("Changed");
    expect(closing()).toBe(true);
  });
});
