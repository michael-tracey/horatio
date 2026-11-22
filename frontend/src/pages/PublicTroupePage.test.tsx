import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { CharacterOut, Me, TroupeOut, TroupeProfileOut } from "../api/types";
import { PublicTroupePage } from "./PublicTroupePage";
import { JoinTroupe } from "./troupe/PlayHere";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const agnes = { id: "u1", handle: "agnes", display_name: "Agnes" } as Me;

const PROFILE = {
  id: "lords",
  name: "Lords of the Night",
  abbreviation: "LotN",
  description: "",
  public: true,
  portrait: null,
  portrait_crop: null,
  banner: null,
  links: {},
  schedule: "",
  games: [],
  venue: { region: "", name: "", address: null, address_hidden: false, access: "" },
  setting: { chronicle: "", city: "", era: "" },
  new_players: null,
  contact: null,
  lead: { id: "u9", handle: "lead", display_name: "Lead" },
  min_age: null,
  content_notes: "",
  written_rules: [],
  setting_document: false,
  can_edit: false,
  pictures_available: false,
} as unknown as TroupeProfileOut;

const LORDS = { id: "lords", name: "Lords of the Night", my_role: null, archived: false, allowed_splats: ["vampire"] } as unknown as TroupeOut;

/** Answers each GET by its path; anything else is a 404. */
function answering(answers: Record<string, unknown>) {
  vi.spyOn(api, "GET").mockImplementation((async (path: string) => {
    if (!(path in answers)) return { error: { detail: "No" }, response: new Response(null, { status: path === "/api/auth/me" ? 401 : 404 }) };
    return { data: answers[path], response: new Response(null, { status: 200 }) };
  }) as never);
}

function Where() {
  const { pathname, search } = useLocation();
  return <p>At {pathname + search}</p>;
}

function show(at: string, element = <PublicTroupePage />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[at]}>
        <Routes>
          <Route path="/t/:troupeId" element={element} />
          <Route path="/troupes/:troupeId/join" element={element} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Request to join on a troupe's public profile (#1192)", () => {
  it("signed out, goes through signing up, or signing in, and on into asking", async () => {
    answering({ "/api/troupes/{troupe_id}/profile": PROFILE });
    show("/t/lords");
    await screen.findByRole("heading", { level: 1, name: "Lords of the Night" });
    const next = encodeURIComponent("/troupes/lords/join");
    expect(screen.getByRole("link", { name: "Request to join" }).getAttribute("href")).toBe(`/sign-up?next=${next}`);
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe(`/sign-in?next=${next}`);
    expect(screen.getByRole("link", { name: "Find another troupe" }).getAttribute("href")).toBe("/find-a-troupe");
  });

  it("signed in, goes straight into asking, beside the troupe's own page", async () => {
    answering({ "/api/auth/me": agnes, "/api/troupes/{troupe_id}/profile": PROFILE, "/api/troupes/{troupe_id}": LORDS, "/api/characters": [] });
    show("/t/lords");
    expect((await screen.findByRole("link", { name: "Request to join" })).getAttribute("href")).toBe("/troupes/lords/join");
    expect(screen.getByRole("link", { name: "Open the troupe" }).getAttribute("href")).toBe("/troupes/lords");
  });

  it("isn't offered to the troupe's staff or a player at home there", async () => {
    answering({ "/api/auth/me": agnes, "/api/troupes/{troupe_id}/profile": PROFILE, "/api/troupes/{troupe_id}": { ...LORDS, my_role: "storyteller" }, "/api/characters": [] });
    show("/t/lords");
    await screen.findByRole("link", { name: "Open the troupe" });
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: "Request to join" })).toBeNull();
    cleanup();

    const home = { id: "c1", status: "active", splat: "vampire", home_troupe_id: "lords", asking_troupe_id: null } as CharacterOut;
    answering({ "/api/auth/me": agnes, "/api/troupes/{troupe_id}/profile": PROFILE, "/api/troupes/{troupe_id}": LORDS, "/api/characters": [home] });
    show("/t/lords");
    await screen.findByRole("link", { name: "Open the troupe" });
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: "Request to join" })).toBeNull();
  });

  it("once signed in, builds a new character for the troupe when there is none to bring", async () => {
    answering({ "/api/characters": [] });
    show("/troupes/lords/join", <JoinTroupe troupe={LORDS} />);
    expect(await screen.findByText("At /characters?troupe=lords")).toBeTruthy();
  });

  it("once signed in, with a character to bring, goes to the troupe's page to choose it", async () => {
    const free = { id: "c1", status: "active", splat: "vampire", home_troupe_id: null, asking_troupe_id: null } as CharacterOut;
    answering({ "/api/characters": [free] });
    show("/troupes/lords/join", <JoinTroupe troupe={LORDS} />);
    expect(await screen.findByText("At /troupes/lords")).toBeTruthy();
  });
});
