import { describe, expect, it } from "vitest";
import { sizedPicture, sizesById } from "./pictureSizes";

const URL = "/api/blog/body-pictures/p1";
const WIDE = [
  { file: "1200.webp", width: 1200, height: 675 },
  { file: "600.webp", width: 600, height: 338 },
];

describe("a blog picture's sizes (#1183)", () => {
  it("give its copies' real widths and the chosen copy's width and height", () => {
    expect(sizedPicture(URL, WIDE)).toEqual({ src: `${URL}/1200.webp`, srcSet: `${URL}/600.webp 600w, ${URL}/1200.webp 1200w`, width: 1200, height: 675 });
    expect(sizedPicture(URL, WIDE, "600.webp")).toMatchObject({ src: `${URL}/600.webp`, width: 600, height: 338 });
  });

  it("name a small picture's copy once, at its own width", () => {
    const small = [
      { file: "1200.webp", width: 400, height: 300 },
      { file: "600.webp", width: 400, height: 300 },
    ];
    expect(sizedPicture(URL, small)).toEqual({ src: `${URL}/1200.webp`, srcSet: `${URL}/600.webp 400w`, width: 400, height: 300 });
  });

  it("fall back to the usual widths and no size when they aren't known", () => {
    expect(sizedPicture(URL, [])).toEqual({ src: `${URL}/1200.webp`, srcSet: `${URL}/600.webp 600w, ${URL}/1200.webp 1200w` });
    expect(sizedPicture(URL, undefined).width).toBeUndefined();
  });

  it("are looked up by picture id from an article's pictures", () => {
    expect(sizesById([{ id: "p1", url: URL, sizes: WIDE }])).toEqual({ p1: WIDE });
    expect(sizesById(undefined)).toEqual({});
  });
});
