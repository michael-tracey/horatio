import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import { AuditLogCard } from "./AuditLogCard";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const settings = { record: "info", keep_debug: 30, keep_info: 365, show_ips: true, last_purge: null };

function show() {
  vi.spyOn(api, "GET").mockImplementation((async () => ({ data: settings, response: new Response(null, { status: 200 }) })) as never);
  const put = vi.spyOn(api, "PUT").mockImplementation((async () => ({ data: settings, response: new Response(null, { status: 200 }) })) as never);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuditLogCard />
    </QueryClientProvider>,
  );
  return put;
}

describe("the audit log card's IP setting (#1205)", () => {
  it("only shows or hides addresses, which are kept either way", async () => {
    const put = show();
    expect(await screen.findByText(/IP addresses are shown\./)).toBeTruthy();
    const box = screen.getByLabelText("Show IP addresses");
    expect((box as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/Horatio always keeps where each sign-in/)).toBeTruthy();
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Save audit log settings" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/audit/settings", { body: { record: "info", keep_debug: 30, keep_info: 365, show_ips: false } }),
    );
  });

  it("says signing in is info, not among the routine debug events", async () => {
    show();
    expect(await screen.findByText(/Signing in and failed sign-ins are info/)).toBeTruthy();
  });
});
