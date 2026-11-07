import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgencyOut, PostOut } from "../../api/types";
import { PostForm } from "./PostForm";

afterEach(cleanup);

const HERALD: AgencyOut = { id: "herald", name: "The Boston Herald", description: "", colour: "#8b1e1e", picture: null, discord_channel: null, retired: false };
const OLD: AgencyOut = { ...HERALD, id: "old", name: "The Old Gazette", retired: true };

function post(over: Partial<PostOut>): PostOut {
  return {
    id: "p",
    troupe_id: "t",
    kind: "news",
    status: "draft",
    agency_id: "herald",
    title: "Fire at the docks",
    body: "Smoke over the harbour.",
    dateline: "Boston",
    picture: null,
    author: "Mara",
    proposed_by: null,
    mine: true,
    note: "",
    publish_at: null,
    published_at: null,
    unread: false,
    discord: null,
    ...over,
  };
}

function form(props: { post?: PostOut; writes?: boolean; agencies?: AgencyOut[] }) {
  const onAction = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PostForm kind="news" post={props.post} writes={props.writes ?? true} agencies={props.agencies ?? [HERALD, OLD]} onAction={onAction} onPicture={vi.fn()} onRemovePicture={vi.fn()} onCancel={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onAction;
}

const button = (name: string | RegExp) => screen.getByRole("button", { name });

describe("PostForm", () => {
  it("needs a headline and an agency before anything goes", () => {
    const onAction = form({ agencies: [HERALD, { ...HERALD, id: "tv", name: "WKBN Nightly" }] });
    fireEvent.click(button("Save draft"));
    expect(screen.getByText("Write a headline.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "  Fire at the docks " } });
    fireEvent.click(button("Publish now"));
    expect(screen.getByText("Choose the agency it comes from.")).toBeTruthy();
    expect(onAction).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "herald" } });
    fireEvent.click(button("Publish now"));
    expect(onAction).toHaveBeenCalledWith({ agency_id: "herald", title: "Fire at the docks", dateline: "", body: "" }, { do: "publish", note: "" });
  });

  it("offers a retired agency only to a story that already has it, and picks the only one", () => {
    form({});
    const agency = screen.getByLabelText("Agency") as HTMLSelectElement;
    expect(Array.from(agency.options).map((o) => o.text)).toEqual(["Choose an agency…", "The Boston Herald"]);
    expect(agency.value).toBe("herald");
    cleanup();
    form({ post: post({ agency_id: "old" }) });
    const kept = Array.from((screen.getByLabelText("Agency") as HTMLSelectElement).options).map((o) => o.text);
    expect(kept).toContain("The Old Gazette (retired)");
  });

  it("schedules for a time to come, read on the writer's clock", () => {
    const onAction = form({ post: post({}) });
    fireEvent.click(button("Schedule…"));
    const when = screen.getByLabelText(/^Publish at/) as HTMLInputElement;
    // It suggests a time to come.
    expect(when.value).toMatch(/^\d{4}-\d\d-\d\dT\d\d:00$/);
    fireEvent.change(when, { target: { value: "2020-01-01T09:00" } });
    expect(screen.getByText("Choose a time to come, or publish it now.")).toBeTruthy();
    expect((button("Schedule") as HTMLButtonElement).disabled).toBe(true);

    const next = new Date(Date.now() + 3 * 86_400_000);
    const pad = (n: number) => String(n).padStart(2, "0");
    const value = `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T20:30`;
    fireEvent.change(when, { target: { value } });
    fireEvent.click(button("Schedule"));
    const [, action] = onAction.mock.calls[0]!;
    expect(action.do).toBe("schedule");
    // On this device's clock, as no time zone is chosen.
    expect(new Date(action.at).getHours()).toBe(20);
    expect(new Date(action.at).getMinutes()).toBe(30);
  });

  it("lets a narrator only send a proposal, and change it while it waits", () => {
    const onAction = form({ writes: false });
    expect(screen.queryByRole("button", { name: "Publish now" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Schedule…" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "Rumours at Elysium" } });
    fireEvent.change(screen.getByLabelText("Agency"), { target: { value: "herald" } });
    fireEvent.click(button("Send the proposal"));
    expect(onAction.mock.calls[0]![1]).toEqual({ do: "propose" });
    cleanup();

    form({ writes: false, post: post({ status: "proposed", proposed_by: "Nell" }) });
    expect(button("Save the proposal")).toBeTruthy();
  });

  it("takes up or declines a narrator's proposal, with a note", () => {
    const onAction = form({ post: post({ status: "proposed", proposed_by: "Nell", mine: false }) });
    fireEvent.change(screen.getByLabelText("Note to Nell (optional)"), { target: { value: "Not this week." } });
    expect(button("Take it up as a draft")).toBeTruthy();
    fireEvent.click(button("Decline…"));
    fireEvent.click(button("Decline it"));
    expect(onAction.mock.calls[0]![1]).toEqual({ do: "decline", note: "Not this week." });
  });

  it("changes a published story in place", () => {
    const onAction = form({ post: post({ status: "published", published_at: "2026-11-07T18:00:00Z" }) });
    expect(screen.queryByRole("button", { name: "Publish now" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "Fire out at the docks" } });
    fireEvent.click(button("Save changes"));
    expect(onAction.mock.calls[0]).toEqual([{ agency_id: "herald", title: "Fire out at the docks", dateline: "Boston", body: "Smoke over the harbour." }, { do: "save" }]);
  });

  it("previews it as players and Discord will show it", () => {
    form({ post: post({}) });
    fireEvent.click(button("Preview"));
    expect(screen.getByRole("heading", { name: "Fire at the docks" })).toBeTruthy();
    expect(screen.getByLabelText("On Discord").textContent).toContain("Read in Horatio");
  });
});
