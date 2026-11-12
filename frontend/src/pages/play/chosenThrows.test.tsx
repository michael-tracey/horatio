import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/client";
import type { MyThrowImagesOut, ThrowSetOut } from "../../api/types";
import { keepsQuery, mineOf } from "../../offline/keep";
import { fetchThrowImages, imagesOf, setName, THROW_IMAGES, type ChosenThrows } from "./chosenThrows";
import { HORATIO_IMAGES, ThrowFace } from "./throwImages";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const BONES: ThrowSetOut = {
  troupe_id: "11111111-1111-4111-8111-111111111111",
  troupe_name: "Bone Throwers",
  name: "Land of the Sky bones",
  rock: "/api/troupes/t/throw-images/r",
  paper: "/api/troupes/t/throw-images/p",
  scissors: "/api/troupes/t/throw-images/s",
};

function answering(mine: MyThrowImagesOut) {
  vi.spyOn(api, "GET").mockImplementation((async () => ({ data: mine, response: new Response(null, { status: 200 }) })) as never);
}

/** A fetch that answers each picture with a tiny WebP-ish body, and counts what it was asked. */
function pictures() {
  const asked: string[] = [];
  const get = (async (address: string) => {
    asked.push(address);
    return { ok: true, status: 200, blob: async () => new Blob([address], { type: "image/webp" }) };
  }) as unknown as typeof fetch;
  return { asked, get };
}

describe("the throw pictures a person chose (#671)", () => {
  it("names a set by its own name and its troupe's, or the troupe's alone", () => {
    expect(setName(BONES)).toBe("Land of the Sky bones (Bone Throwers)");
    expect(setName({ ...BONES, name: "" })).toBe("Bone Throwers");
  });

  it("uses Horatio's while nothing is chosen, or nothing is kept yet", () => {
    expect(imagesOf(undefined)).toBe(HORATIO_IMAGES);
    expect(imagesOf({ chosen: null, offered: [BONES] })).toBe(HORATIO_IMAGES);
  });

  it("reads the chosen set's three pictures in, at 512 px, so they can be kept offline", async () => {
    answering({ chosen: BONES, offered: [BONES] });
    const { asked, get } = pictures();
    const kept = await fetchThrowImages(get);
    expect(asked).toEqual([`${BONES.rock}/512.webp`, `${BONES.paper}/512.webp`, `${BONES.scissors}/512.webp`]);
    expect(kept.chosen?.pictures.rock).toMatch(/^data:image\/webp;base64,/);
    expect(kept.offered).toEqual([BONES]);

    render(<ThrowFace images={imagesOf(kept)} which="paper" />);
    const face = screen.getByRole("img", { name: "Paper" });
    expect(face.querySelector("img")?.getAttribute("src")).toBe(kept.chosen?.pictures.paper);
  });

  it("asks for no pictures with Horatio's, and falls back to them when the choice has gone", async () => {
    answering({ chosen: null, offered: [] });
    const { asked, get } = pictures();
    const kept: ChosenThrows = await fetchThrowImages(get);
    expect(kept).toEqual({ chosen: null, offered: [] });
    expect(asked).toEqual([]);
  });

  it("is kept on the device with the person's own answers", () => {
    expect(keepsQuery([...THROW_IMAGES], mineOf([], "u1"))).toBe(true);
  });
});
