import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SaveDeviceScene } from "./DeviceScene";

afterEach(cleanup);

function memory(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  };
}

function kept(ids: string[]): Storage {
  const storage = memory();
  storage.setItem("horatio.scene.t1", JSON.stringify(ids));
  return storage;
}

describe("saving the scene a device kept", () => {
  it("offers nothing when the device has no scene, or an empty one", () => {
    const onSave = vi.fn();
    render(<SaveDeviceScene troupeId="t1" onSave={onSave} storage={memory()} />);
    render(<SaveDeviceScene troupeId="t1" onSave={onSave} storage={kept([])} />);
    expect(screen.queryByRole("region", { name: "This device's scene" })).toBeNull();
  });

  it("saves it under a name, My scene unless changed, and forgets it", async () => {
    const storage = kept(["a", "b"]);
    const onSave = vi.fn().mockResolvedValue({});
    render(<SaveDeviceScene troupeId="t1" onSave={onSave} storage={storage} />);
    expect(screen.getByRole("region", { name: "This device's scene" }).textContent).toContain("2 characters");
    expect(screen.getByLabelText("Name of the scene")).toHaveProperty("value", "My scene");
    fireEvent.change(screen.getByLabelText("Name of the scene"), { target: { value: " Ballroom " } });
    fireEvent.click(screen.getByRole("button", { name: "Save this device's scene" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "This device's scene" })).toBeNull());
    expect(onSave).toHaveBeenCalledWith("Ballroom", ["a", "b"]);
    expect(storage.getItem("horatio.scene.t1")).toBeNull();
  });

  it("keeps it when saving fails, to try again", async () => {
    const storage = kept(["a"]);
    const onSave = vi.fn().mockRejectedValue(new Error("No connection."));
    render(<SaveDeviceScene troupeId="t1" onSave={onSave} storage={storage} />);
    fireEvent.click(screen.getByRole("button", { name: "Save this device's scene" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "No connection.");
    expect(onSave).toHaveBeenCalledWith("My scene", ["a"]);
    expect(storage.getItem("horatio.scene.t1")).not.toBeNull();
  });

  it("forgets it when dismissed, without saving", () => {
    const storage = kept(["a"]);
    const onSave = vi.fn();
    render(<SaveDeviceScene troupeId="t1" onSave={onSave} storage={storage} />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("region", { name: "This device's scene" })).toBeNull();
    expect(onSave).not.toHaveBeenCalled();
    expect(storage.getItem("horatio.scene.t1")).toBeNull();
  });
});
