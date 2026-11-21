import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WebAuthnError } from "@simplewebauthn/browser";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../api/client";
import { SignInPage } from "./SignIn";

/** The browser's passkey request: `autofill` for the login box's offer, otherwise the button's. */
const { start } = vi.hoisted(() => ({ start: vi.fn<(autofill: boolean) => Promise<unknown>>() }));
vi.mock(import("@simplewebauthn/browser"), async (original) => ({
  ...(await original()),
  browserSupportsWebAuthn: () => true,
  browserSupportsWebAuthnAutofill: async () => true,
  startAuthentication: (async ({ useBrowserAutofill }: { useBrowserAutofill?: boolean }) => start(!!useBrowserAutofill)) as never,
}));

const ok = (data: object) => ({ data, response: new Response(null, { status: 200 }) });
const refused = { error: { detail: "That passkey didn't sign you in." }, response: new Response(null, { status: 401 }) };

/** As headless Chrome turns down the login box's offer as the page opens. */
const notSupported = new WebAuthnError({
  message: "Resident credentials or empty 'allowCredentials' lists are not supported at this time.",
  code: "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY",
  cause: new DOMException("Resident credentials or empty 'allowCredentials' lists are not supported at this time.", "NotSupportedError"),
});
const aborted = new WebAuthnError({ message: "aborted", code: "ERROR_CEREMONY_ABORTED", cause: new DOMException("", "AbortError") });
const notAllowed = new DOMException("The operation either timed out or was not allowed.", "NotAllowedError");
const cancelled = new WebAuthnError({ message: notAllowed.message, code: "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY", cause: notAllowed });

let signIn: () => object;
let logged: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  signIn = () => ok({});
  logged = vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(api, "POST").mockImplementation((async (path: string) => (path === "/api/auth/passkey/options" ? ok({ challenge: "c" }) : signIn())) as never);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  start.mockReset();
});

function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(["me"], null);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/sign-in"]}>
        <SignInPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the sign-in page's passkeys (#1124)", () => {
  it.each([
    ["the browser turns the login box's offer down", () => start.mockRejectedValue(notSupported)],
    ["the passkey picked from the login box is refused", () => {
      start.mockResolvedValue({ id: "k" });
      signIn = () => refused;
    }],
  ])("keep it off the page when %s, in the console only", async (_, arrange) => {
    arrange();
    show();
    await waitFor(() => expect(logged).toHaveBeenCalledOnce());
    expect(start).toHaveBeenCalledWith(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("say nothing at all when the login box's offer is stopped", async () => {
    start.mockRejectedValue(aborted);
    show();
    await waitFor(() => expect(start).toHaveBeenCalledWith(true));
    await new Promise((r) => setTimeout(r, 20));
    expect(logged).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("say what went wrong with the button's request", async () => {
    start.mockImplementation(async (autofill) => {
      throw autofill ? notSupported : cancelled;
    });
    show();
    await waitFor(() => expect(logged).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));
    expect((await screen.findByRole("alert")).textContent).toBe("No passkey was given. Try again, or sign in with your password.");
  });

  it("say what the server said of the passkey picked with the button", async () => {
    start.mockImplementation(async (autofill) => {
      if (autofill) throw aborted;
      return { id: "k" };
    });
    signIn = () => refused;
    show();
    fireEvent.click(screen.getByRole("button", { name: "Sign in with a passkey" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That passkey didn't sign you in.");
  });
});
