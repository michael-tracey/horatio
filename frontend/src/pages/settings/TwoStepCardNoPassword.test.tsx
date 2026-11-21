import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../../api/client";
import { TwoStepCard } from "./TwoStepCard";

vi.mock("@simplewebauthn/browser", () => ({ browserSupportsWebAuthn: () => true, startRegistration: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
};

/** What `/api/two-step` answers; anything else the card asks is a 404. */
function answers(two: typeof state) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/two-step") return { data: two, response: new Response(null, { status: 200 }) };
    return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
  }) as never);
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <TwoStepCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

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
