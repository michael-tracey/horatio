import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ToastProvider, useToast, type ToastIn } from "./Toast";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function setup() {
  let toast: (t: ToastIn) => void = () => {};
  function Grab() {
    toast = useToast();
    return null;
  }
  render(
    <MemoryRouter>
      <ToastProvider>
        <Grab />
      </ToastProvider>
    </MemoryRouter>,
  );
  return (t: ToastIn) => act(() => toast(t));
}

describe("the shared toast", () => {
  it("is read out politely, and goes by itself", () => {
    const show = setup();
    show({ message: "Saved" });
    const region = screen.getByText("Saved").closest("[aria-live]");
    expect(region?.getAttribute("aria-live")).toBe("polite");
    act(() => vi.advanceTimersByTime(3_900));
    expect(screen.queryByText("Saved")).not.toBeNull();
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByText("Saved")).toBeNull();
  });

  it("shows one at a time, the newest in place of the last", () => {
    const show = setup();
    show({ message: "Spent 1 Blood · 9/10" });
    show({ message: "Spent 1 Blood · 8/10" });
    expect(screen.queryByText("Spent 1 Blood · 9/10")).toBeNull();
    expect(screen.getByText("Spent 1 Blood · 8/10")).not.toBeNull();
  });

  it("stays longer with an action, which runs once when pressed and closes it", () => {
    const show = setup();
    const undo = vi.fn();
    show({ message: "Spent 1 Blood · 9/10", action: { label: "Undo", onClick: undo } });
    act(() => vi.advanceTimersByTime(6_000));
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(undo).toHaveBeenCalledOnce();
    expect(screen.queryByText("Spent 1 Blood · 9/10")).toBeNull();
  });

  it("waits while focus is on its button", () => {
    const show = setup();
    show({ message: "Spent 1 Blood · 9/10", action: { label: "Undo", onClick: () => {} } });
    const undo = screen.getByRole("button", { name: "Undo" });
    fireEvent.focus(undo);
    act(() => vi.advanceTimersByTime(20_000));
    expect(screen.queryByText("Spent 1 Blood · 9/10")).not.toBeNull();
    fireEvent.blur(undo);
    act(() => vi.advanceTimersByTime(8_000));
    expect(screen.queryByText("Spent 1 Blood · 9/10")).toBeNull();
  });

  it("does nothing outside a provider", () => {
    function Lone() {
      const toast = useToast();
      return <button onClick={() => toast({ message: "Lost" })}>Go</button>;
    }
    render(<Lone />);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(screen.queryByText("Lost")).toBeNull();
  });
});
