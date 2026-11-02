import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DefaultBloodlinesOut } from "../../api/types";
import { bookDefault, DefaultBloodlinesCard, defaultText } from "./DefaultBloodlines";

afterEach(cleanup);

const tzimisce = { clan: "Tzimisce", bloodlines: ["Tzimisce: Carpathian", "Tzimisce: Koldun"], book: { Camarilla: "Tzimisce: Carpathian" }, house: null };
const gangrel = { clan: "Gangrel", bloodlines: ["Gangrel: Coyote", "Gangrel: Noiad"], book: { Sabbat: "Gangrel: Coyote" }, house: null };

describe("the book's default", () => {
  it("gives the setting's when the troupe has one sect", () => {
    expect(bookDefault(tzimisce, "Camarilla")).toBe("Tzimisce: Carpathian");
    expect(bookDefault(tzimisce, "Sabbat")).toBe("The plain Tzimisce, no bloodline");
  });

  it("gives each sect's otherwise", () => {
    expect(bookDefault({ ...tzimisce, book: { Anarch: "Tzimisce: Koldun", Camarilla: "Tzimisce: Carpathian" } }, null)).toBe(
      "Tzimisce: Koldun (Anarch), Tzimisce: Carpathian (Camarilla)",
    );
    expect(bookDefault({ ...tzimisce, book: {} }, null)).toBe("The plain Tzimisce, no bloodline");
  });

  it("names the plain clan when the clan is its own default", () => {
    expect(defaultText("Tzimisce", "Tzimisce")).toBe("The plain Tzimisce, no bloodline");
    expect(defaultText("Tzimisce", "Tzimisce: Koldun")).toBe("Tzimisce: Koldun");
  });
});

describe("DefaultBloodlinesCard", () => {
  const data: DefaultBloodlinesOut = { setting: "Camarilla", clans: [gangrel, { ...tzimisce, house: "Tzimisce" }] };

  it("lists each clan's default, marking the troupe's own", () => {
    render(<DefaultBloodlinesCard data={data} canEdit={false} save={async () => null} />);
    expect(screen.getByText("The plain Tzimisce, no bloodline (house rule)")).toBeTruthy();
    expect(screen.getByText("The plain Gangrel, no bloodline")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change default bloodlines" })).toBeNull();
  });

  it("saves the clans chosen, leaving the rest to the book", async () => {
    const saved: Record<string, string>[] = [];
    render(<DefaultBloodlinesCard data={data} canEdit save={async (d) => saved.push(d)} />);
    fireEvent.click(screen.getByRole("button", { name: "Change default bloodlines" }));
    const tzimisceBox = screen.getByLabelText<HTMLSelectElement>("Tzimisce default bloodline");
    expect(tzimisceBox.value).toBe("Tzimisce");
    expect([...tzimisceBox.options].map((o) => o.text)).toEqual([
      "By the book: Tzimisce: Carpathian",
      "The plain Tzimisce, no bloodline",
      "Tzimisce: Carpathian",
      "Tzimisce: Koldun",
    ]);
    fireEvent.change(screen.getByLabelText("Gangrel default bloodline"), { target: { value: "Gangrel: Noiad" } });
    fireEvent.change(tzimisceBox, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toEqual([{ Gangrel: "Gangrel: Noiad" }]));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).toBeNull());
  });
});
