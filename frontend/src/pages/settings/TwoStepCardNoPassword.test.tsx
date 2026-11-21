import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router";
import { api } from "../../api/client";
import { TwoStepCard } from "./TwoStepCard";

vi.mock("@simplewebauthn/browser", () => ({ browserSupportsWebAuthn: () => true, startRegistration: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const state = {
  app: false,
  apps_available: true,
  passkeys: [] as unknown[],
  passkeys_available: true,
  recovery_codes_left: 0,
  required_by: ["the custodian"],
  needed: true,
  has_password: false,
  can_confirm_with_discord: false,
  confirmed_until: null as string | null,
};

/** What `/api/two-step` answers; anything else the card asks is a 404. */
function answers(two: typeof state) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/two-step") return { data: two, response: new Response(null, { status: 200 }) };
    return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
  }) as never);
}

/** Where the page is now, to see what the address keeps. */
function Here() {
  const location = useLocation();
  return <div aria-label="Address">{location.pathname + location.search}</div>;
}

function show(at = "/account/sign-in") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[at]}>
        <TwoStepCard />
        <Here />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** What POSTs answer: Discord's page for confirming, or nothing much for the rest. */
function posts() {
  return vi.spyOn(api, "POST").mockImplementation((async (path: string) => {
    if (path === "/api/auth/discord/confirm") return { data: { url: "https://discord.com/oauth2/authorize?state=confirm.x" }, response: new Response(null, { status: 200 }) };
    return { data: { recovery_codes: [] }, response: new Response(null, { status: 200 }) };
  }) as never);
}

const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();

describe("two-step sign-in for an account made with Discord, with no password (#1128)", () => {
  it("says adding a passkey needs a password, and how to set one, and still offers the app", async () => {
    answers(state);
    show();
    expect(await screen.findByText(/Adding a passkey asks for your password, and you have none yet/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Forgot your password?" }).getAttribute("href")).toBe("/forgot-password");
    expect(screen.getByText(/An authenticator app, below, asks for no password\./)).toBeTruthy();
    expect(screen.queryByLabelText("Your password")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a passkey" })).toBeNull();
    expect(screen.getByRole("button", { name: "Set up an authenticator app" })).toBeTruthy();
  });

  it("says the same in place of the password form for turning off the app", async () => {
    answers({ ...state, app: true, recovery_codes_left: 10, needed: false });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    expect(screen.getByText(/Turning off the app asks for your password, and you have none yet/)).toBeTruthy();
    expect(screen.queryByLabelText("Your password")).toBeNull();
  });

  it("asks for the password as before where there is one", async () => {
    answers({ ...state, has_password: true });
    show();
    expect(await screen.findByRole("button", { name: "Add a passkey" })).toBeTruthy();
    expect(screen.queryByText(/you have none yet/)).toBeNull();
  });
});

describe("confirming it's you with Discord in place of a password (#1140)", () => {
  const linked = { ...state, can_confirm_with_discord: true };

  it("offers Confirm with Discord in place of the password for adding a passkey, keeping its name", async () => {
    answers(linked);
    const post = posts();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    show("/two-step?next=%2Ftroupes");

    fireEvent.change(await screen.findByLabelText(/Passkey name/), { target: { value: "Phone" } });
    expect(screen.queryByLabelText(/Your password/)).toBeNull();
    expect(screen.queryByText(/you have none yet/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Confirm with Discord" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://discord.com/oauth2/authorize?state=confirm.x"));
    expect(post).toHaveBeenCalledWith("/api/auth/discord/confirm", { body: { next: "/two-step?next=%2Ftroupes&confirming=add&name=Phone" } });
  });

  it("offers it in place of the password form for turning off the app, with the passkey's id for removing one", async () => {
    const passkeys = [{ id: "p1", name: "Laptop", created_at: "2026-11-01T00:00:00Z", last_used_at: null, discoverable: true }];
    answers({ ...linked, app: true, passkeys, recovery_codes_left: 10, needed: false });
    const post = posts();
    vi.stubGlobal("location", { ...window.location, assign: vi.fn() });
    show();

    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    expect(screen.getByText(/Turning off the app asks you to confirm it's you/)).toBeTruthy();
    expect(screen.queryByLabelText("Your password")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove Laptop" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm with Discord" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/auth/discord/confirm", { body: { next: "/account/sign-in?confirming=passkey&passkey=p1" } }));
  });

  it("back from Discord, opens the form they were in, confirmed, and sends no password", async () => {
    answers({ ...linked, app: true, recovery_codes_left: 10, needed: false, confirmed_until: inFiveMinutes() });
    const post = posts();
    show("/account/sign-in?confirming=app&discord_confirm=confirmed");

    expect(await screen.findByText("Discord confirmed it's you. Go on within 5 minutes.")).toBeTruthy();
    expect(screen.getByText(/To turn off your authenticator app\. Discord confirmed it's you, so no password is asked\./)).toBeTruthy();
    expect(screen.queryByLabelText("Your password")).toBeNull();
    // The address forgets it, so a reload doesn't say it again.
    await waitFor(() => expect(screen.getByLabelText("Address").textContent).toBe("/account/sign-in"));

    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/two-step/app/remove", { body: { password: "" } }));
  });

  it("back from Discord to add a passkey, shows the form with its name and no password box", async () => {
    answers({ ...linked, confirmed_until: inFiveMinutes() });
    show("/two-step?next=%2Ftroupes&confirming=add&name=Phone&discord_confirm=confirmed");

    expect(await screen.findByRole("button", { name: "Add a passkey" })).toBeTruthy();
    expect((screen.getByLabelText(/Passkey name/) as HTMLInputElement).value).toBe("Phone");
    expect(screen.queryByLabelText(/Your password/)).toBeNull();
    await waitFor(() => expect(screen.getByLabelText("Address").textContent).toBe("/two-step?next=%2Ftroupes"));
  });

  it("says why nothing was confirmed, with the button there to try again", async () => {
    answers({ ...linked, app: true, recovery_codes_left: 10, needed: false });
    show("/account/sign-in?confirming=codes&discord_confirm=other_account");

    expect(await screen.findByText("That Discord account isn't the one linked to yours, so nothing was confirmed.")).toBeTruthy();
    const codes = within(screen.getByRole("region", { name: "Recovery codes" }));
    expect(codes.getByText(/Making new recovery codes asks you to confirm it's you/)).toBeTruthy();
    expect(codes.getByRole("button", { name: "Confirm with Discord" })).toBeTruthy();
  });

  it("says nothing for words Discord's callback never sends", async () => {
    answers(linked);
    show("/account/sign-in?discord_confirm=Call+555-0100+now");
    expect(await screen.findByRole("button", { name: "Confirm with Discord" })).toBeTruthy();
    await waitFor(() => expect(screen.getByLabelText("Address").textContent).toBe("/account/sign-in"));
    expect(screen.queryByText(/555-0100/)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
