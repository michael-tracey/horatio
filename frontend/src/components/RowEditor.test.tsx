import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RowEditor, useRowEditor } from "./RowEditor";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** A list whose rows open an editor under them; Remove takes a row away while its editor is open. */
function List() {
  const [rows, setRows] = useState(["Ash", "Briar"]);
  const editor = useRowEditor<string>();
  return (
    <>
      <button type="button" ref={editor.fallback}>
        Add
      </button>
      <ul>
        {rows.map((r) => (
          <li key={r}>
            <button type="button" aria-expanded={editor.isOpen(r)} onClick={(e) => editor.toggle(r, e.currentTarget)}>
              Change {r}
            </button>
            {editor.isOpen(r) && (
              <RowEditor>
                <label>
                  Name of {r}
                  <input />
                </label>
                <button type="button" onClick={editor.close}>
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setRows((all) => all.filter((x) => x !== r));
                    editor.close();
                  }}
                >
                  Remove
                </button>
              </RowEditor>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

describe("an editor opened from a row (#648)", () => {
  it("opens one at a time, focus on its first field, and gives the focus back to its row's button", () => {
    render(<List />);
    fireEvent.click(screen.getByRole("button", { name: "Change Ash" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Name of Ash"));
    fireEvent.click(screen.getByRole("button", { name: "Change Briar" }));
    expect(screen.queryByLabelText("Name of Ash")).toBeNull();
    expect(document.activeElement).toBe(screen.getByLabelText("Name of Briar"));

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Name of Briar")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Change Briar" }));
  });

  it("gives the focus to the fallback when its row has gone", () => {
    render(<List />);
    fireEvent.click(screen.getByRole("button", { name: "Change Ash" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByRole("button", { name: "Change Ash" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Add" }));
  });

  it("scrolls its top into view when it is taller than the screen", () => {
    const scroll = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { value: scroll, configurable: true });
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 500, bottom: 500 + 2000, height: 2000 } as DOMRect);
    render(<List />);
    fireEvent.click(screen.getByRole("button", { name: "Change Ash" }));
    expect(scroll).toHaveBeenCalledWith({ block: "start" });
    delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
  });
});
