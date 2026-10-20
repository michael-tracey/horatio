import { describe, expect, it } from "vitest";
import { centred, fromCrop, portraitFrame, resized, square, toCrop } from "./crop";

describe("the crop square", () => {
  it("starts as the biggest square in the middle", () => {
    expect(centred(400, 300)).toEqual({ left: 50, top: 0, width: 300, height: 300 });
    expect(centred(300, 500)).toEqual({ left: 0, top: 100, width: 300, height: 300 });
  });

  it("stays inside the picture and is never too small or too big", () => {
    expect(square(400, 400, 350, -20, 100)).toEqual({ left: 300, top: 0, width: 100, height: 100 });
    expect(square(400, 400, 0, 0, 2)).toEqual({ left: 0, top: 0, width: 40, height: 40 });
    expect(square(400, 300, 0, 0, 999)).toEqual({ left: 0, top: 0, width: 300, height: 300 });
  });

  it("grows and shrinks about its centre", () => {
    expect(resized(400, 400, { left: 100, top: 100, width: 100, height: 100 }, 200)).toEqual({ left: 50, top: 50, width: 200, height: 200 });
    // Against an edge, it grows away from it.
    expect(resized(400, 400, { left: 0, top: 0, width: 100, height: 100 }, 200)).toEqual({ left: 0, top: 0, width: 200, height: 200 });
  });

  it("goes to and from the API's fractions", () => {
    const box = { left: 100, top: 50, width: 200, height: 200 };
    expect(toCrop(400, 300, box)).toEqual({ x: 0.25, y: 50 / 300, size: 0.5 });
    expect(fromCrop(400, 300, toCrop(400, 300, box))).toEqual(box);
    expect(fromCrop(400, 300, null)).toEqual(centred(400, 300));
  });
});

// The same cases as the server's test_square_and_portrait_boxes.
describe("the badge's portrait frame", () => {
  it("is 4:5 around the square, moved to stay inside", () => {
    expect(portraitFrame(400, 400, { left: 100, top: 0, width: 100, height: 100 })).toEqual({ left: 100, top: 0, width: 100, height: 125 });
    expect(portraitFrame(400, 400, { left: 0, top: 300, width: 100, height: 100 })).toEqual({ left: 0, top: 275, width: 100, height: 125 });
    expect(portraitFrame(400, 400, { left: 200, top: 200, width: 200, height: 200 })).toEqual({ left: 200, top: 150, width: 200, height: 250 });
  });

  it("is narrowed when the picture is too short for it", () => {
    expect(portraitFrame(400, 300, { left: 50, top: 0, width: 300, height: 300 })).toEqual({ left: 80, top: 0, width: 240, height: 300 });
  });
});
