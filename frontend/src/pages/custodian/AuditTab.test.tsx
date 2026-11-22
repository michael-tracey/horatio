import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { Entry } from "./AuditTab";

afterEach(cleanup);

const signedIn: components["schemas"]["AuditEntry"] = {
  id: "e1",
  at: "2026-11-22T11:00:00Z",
  action: "account.signed_in",
  message: "Agnes signed in.",
  actor_id: "u1",
  actor_name: "Agnes",
  character_id: null,
  character_name: null,
  player_id: null,
  player_name: null,
  data: {},
  troupe_id: null,
  troupe_name: null,
  level: "info",
  ip_address: null,
};

function show(entry: components["schemas"]["AuditEntry"]) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ul>
          <Entry entry={entry} />
        </ul>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("an entry in the custodian's search (#1205)", () => {
  it("shows where it came from, apart from what it says, when the server sends it", () => {
    show({ ...signedIn, ip_address: "203.0.113.7" });
    expect(screen.getByText("Agnes signed in.")).toBeTruthy();
    expect(screen.getByText("From 203.0.113.7")).toBeTruthy();
  });

  it("shows no address while the custodian hides them", () => {
    show(signedIn);
    expect(screen.getByText("Agnes signed in.")).toBeTruthy();
    expect(screen.queryByText(/^From /)).toBeNull();
  });
});
