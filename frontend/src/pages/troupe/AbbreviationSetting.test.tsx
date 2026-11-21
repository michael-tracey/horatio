import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { ToastProvider } from "../../components/Toast";
import { AbbreviationSetting, abbreviationDefaultText, abbreviationProblem } from "./AbbreviationSetting";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const TROUPE = {
  id: "t1",
  name: "Court of Ashes",
  abbreviation: "CoA",
  abbreviation_set: null,
  abbreviation_default: "CoA",
  archived: false,
  my_role: "lead_storyteller",
} as unknown as TroupeOut;

function draw(troupe: TroupeOut = TROUPE) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  client.setQueryData(["me"], { is_custodian: false });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <AbbreviationSetting troupe={troupe} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return screen.getByRole("region", { name: "Abbreviation" });
}

describe("the troupe's abbreviation (#1153)", () => {
  it("is 1 to 10 letters, digits and separators, no spaces; empty clears it", () => {
    expect(abbreviationProblem("")).toBeNull();
    expect(abbreviationProblem(" LotsLarp ")).toBeNull();
    expect(abbreviationProblem("Ash-Court.1")).toMatch(/^Up to 10/);
    expect(abbreviationProblem("Ash_Ct.1")).toBeNull();
    expect(abbreviationProblem("Ash Court")).toMatch(/no spaces/);
    expect(abbreviationProblem("Ash!")).toMatch(/^Up to 10/);
  });

  it("says what the troupe goes by with none set: its initials, or its name when they clash", () => {
    expect(abbreviationDefaultText(TROUPE)).toBe("Left empty, it goes by CoA, from the initials of its name.");
    expect(abbreviationDefaultText({ name: "Court of Ashes", abbreviation_default: "Court of Ashes" })).toBe(
      "Left empty, it goes by its full name, as another troupe goes by its initials.",
    );
  });

  it("shows the lead the name beside it, the default as a hint, and saves it trimmed", async () => {
    const saved = vi.spyOn(api, "PATCH").mockResolvedValue({ data: TROUPE, response: new Response(null, { status: 200 }) } as never);
    const card = draw();
    expect(card.textContent).toContain("Name: Court of Ashes");
    const box = within(card).getByRole("textbox", { name: "Abbreviation" });
    expect(box.getAttribute("placeholder")).toBe("CoA");
    expect(box.getAttribute("aria-describedby")).toBeTruthy();
    expect(card.textContent).toContain("Left empty, it goes by CoA");

    fireEvent.change(box, { target: { value: "Ash Court" } });
    expect(within(card).getByText(/with no spaces/)).toBeTruthy();
    expect((within(card).getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(box, { target: { value: " Ashes " } });
    fireEvent.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(saved).toHaveBeenCalledWith("/api/troupes/{troupe_id}", { params: { path: { troupe_id: "t1" } }, body: { abbreviation: "Ashes" } }),
    );
  });

  it("shows other staff what it goes by, read-only", () => {
    const card = draw({ ...TROUPE, my_role: "storyteller", abbreviation: "Ashes", abbreviation_set: "Ashes" });
    expect(within(card).queryByRole("textbox")).toBeNull();
    expect(card.textContent).toContain("Goes by: Ashes");
    expect(card.textContent).not.toContain("none set");
    expect(card.textContent).toContain("The troupe's lead storyteller changes this.");
  });
});
