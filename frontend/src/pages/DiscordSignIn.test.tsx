import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { api } from "../api/client";
import { DiscordSignIn, discordOutcome } from "./DiscordSignIn";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** Whether the server says Discord is set up; anything else it's asked is a 404. */
function discordSetUp(available: boolean) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (path === "/api/auth/discord") return { data: { available }, response: new Response(null, { status: 200 }) };
    return { error: { detail: "Not found" }, response: new Response(null, { status: 404 }) };
  }) as never);
}

function show(verb: "in" | "up", at = "/sign-in") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <DiscordSignIn verb={verb} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DiscordSignIn", () => {
  it("offers nothing where Discord isn't set up on the server", async () => {
    discordSetUp(false);
    show("in");
    await waitFor(() => expect(api.GET).toHaveBeenCalled());
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers signing in, or up, with Discord where it is", async () => {
    discordSetUp(true);
    show("in");
    expect(await screen.findByRole("button", { name: "Sign in with Discord" })).toBeTruthy();
    cleanup();
    show("up", "/sign-up");
    expect(await screen.findByRole("button", { name: "Sign up with Discord" })).toBeTruthy();
  });

  it("goes to Discord's page, keeping where they were going", async () => {
    discordSetUp(true);
    const post = vi.spyOn(api, "POST").mockResolvedValue({ data: { url: "https://discord.com/oauth2/authorize?state=x" }, response: new Response(null, { status: 200 }) } as never);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    show("in", "/sign-in?next=%2Ftroupes");

    fireEvent.click(await screen.findByRole("button", { name: "Sign in with Discord" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://discord.com/oauth2/authorize?state=x"));
    expect(post).toHaveBeenCalledWith("/api/auth/discord/start", { body: { next: "/troupes" } });
  });

  it("says why Discord didn't sign them in", async () => {
    discordSetUp(true);
    show("in", "/sign-in?discord=email_taken");
    expect((await screen.findByRole("alert")).textContent).toContain("Sign in with your password, then link Discord in Account › Sign-in.");
  });
});

describe("discordOutcome", () => {
  it("has words for what the callback sends, and none for anything else", () => {
    for (const code of ["expired", "cancelled", "failed", "throttled", "no_email", "email_taken", "suspended", "merged"]) {
      expect(discordOutcome(code)).toBeTruthy();
    }
    expect(discordOutcome("Call this number to unlock your account")).toBeNull();
    expect(discordOutcome(null)).toBeNull();
  });
});
