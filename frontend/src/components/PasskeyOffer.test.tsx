import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../api/client";
import { markPasswordSignIn, offerDue } from "../passkeyOffer";
import { PasskeyOffer } from "./PasskeyOffer";

const device = vi.hoisted(() => ({ platform: true }));
vi.mock("@simplewebauthn/browser", () => ({ browserSupportsWebAuthn: () => true, platformAuthenticatorIsAvailable: async () => device.platform }));

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  device.platform = true;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const me = { id: "u1", email: "owl@example.com", display_name: "Owl", handle: "owl", is_custodian: false, two_step_needed: false };

function answering(who: object, passkeysAvailable = true) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    const data = path === "/api/auth/me" ? who : path === "/api/two-step" ? { passkeys_available: passkeysAvailable } : null;
    return { data, response: new Response(null, { status: 200 }) };
  }) as never);
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PasskeyOffer />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the passkey offer after a password sign-in (#1193)", () => {
  it("offers one on a device that can keep it, and goes to the usual form", async () => {
    answering(me);
    markPasswordSignIn();
    show();
    const add = await screen.findByRole("link", { name: "Add a passkey" });
    expect(add.getAttribute("href")).toBe("/account/sign-in#passkeys");
    fireEvent.click(add);
    expect(offerDue()).toBe(false);
  });

  it("goes for good on Not now", async () => {
    answering(me);
    markPasswordSignIn();
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Add a passkey" })).toBeNull());
    markPasswordSignIn();
    expect(offerDue()).toBe(false);
  });

  it("offers nothing without a password sign-in, on a device that can't, or before two-step set-up", async () => {
    answering(me);
    show();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Add a passkey" })).toBeNull();
    cleanup();

    markPasswordSignIn();
    device.platform = false;
    show();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Add a passkey" })).toBeNull();
    cleanup();

    device.platform = true;
    answering({ ...me, two_step_needed: true });
    show();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("region", { name: "Add a passkey" })).toBeNull();
  });
});
