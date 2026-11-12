import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ThrowFace, troupeImages } from "../play/throwImages";
import { fullSet } from "./ThrowImagesSetting";

afterEach(cleanup);

const BASE = "/api/troupes/t1/throw-images";

describe("a troupe's throw pictures (#670)", () => {
  it("make a set only with all three", () => {
    const some = { name: "", rock: `${BASE}/r`, paper: `${BASE}/p`, scissors: null, complete: false };
    expect(fullSet(some)).toBeNull();
    expect(fullSet({ ...some, scissors: `${BASE}/s`, complete: true })).toEqual({ rock: `${BASE}/r`, paper: `${BASE}/p`, scissors: `${BASE}/s` });
  });

  it("show the troupe's own picture at the Throws tab's size, named for the throw", () => {
    const images = troupeImages("Land of the Sky bones", { rock: `${BASE}/r`, paper: `${BASE}/p`, scissors: `${BASE}/s` });
    expect(images.name).toBe("Land of the Sky bones");
    const { container } = render(<ThrowFace images={images} which="paper" />);
    expect(screen.getByRole("img", { name: "Paper" })).toBeTruthy();
    expect(container.querySelector("img")?.getAttribute("src")).toBe(`${BASE}/p/512.webp`);
  });
});
