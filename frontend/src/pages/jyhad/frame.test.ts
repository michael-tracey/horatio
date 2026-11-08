import { describe, expect, it } from "vitest";
import { frameSvg, svgUrl, tint } from "./frame";

const parsed = (svg: string) => new DOMParser().parseFromString(svg, "image/svg+xml");

describe("the Jyhad card's frame artwork", () => {
  it("is a well-formed SVG of the card's millimetres, with no words in it", () => {
    for (const look of ["night", "bone"] as const) {
      const doc = parsed(frameSvg({ look, superior: [true, false, false], capacity: true }));
      expect(doc.getElementsByTagName("parsererror")).toHaveLength(0);
      expect(doc.documentElement.getAttribute("viewBox")).toBe("0 0 63 88");
      expect(doc.getElementsByTagName("text")).toHaveLength(0);
    }
  });

  it("hangs a ribbon with a disc for each inferior discipline and a diamond for each superior", () => {
    const svg = frameSvg({ look: "night", superior: [true, true, false], capacity: true });
    const doc = parsed(svg);
    // The clan medallion's three circles and the capacity's seat, and one disc.
    expect(doc.getElementsByTagName("circle")).toHaveLength(5);
    const none = parsed(frameSvg({ look: "night", superior: [], capacity: false }));
    expect(none.getElementsByTagName("circle")).toHaveLength(3);
    expect(none.getElementsByTagName("path").length).toBeLessThan(doc.getElementsByTagName("path").length - 3);
  });

  it("is drawn at a size for the canvas, or fills its box on screen", () => {
    expect(frameSvg({ look: "bone", superior: [], capacity: true }, { w: 756, h: 1056 })).toContain('width="756" height="1056"');
    expect(frameSvg({ look: "bone", superior: [], capacity: true })).toContain('width="100%"');
    expect(svgUrl("<svg/>")).toBe("data:image/svg+xml;charset=utf-8,%3Csvg%2F%3E");
  });
});

describe("tinting KRCG's symbols", () => {
  const krcg = '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 0 1010 1000"><path fill="currentColor" d="M0 0h10v10z"/></svg>';

  it("colours currentColor and gives the symbol a size", () => {
    const tinted = tint(krcg, "#123456");
    expect(tinted).not.toContain("currentColor");
    expect(tinted).toContain('fill="#123456" d=');
    expect(tinted).toContain('width="512" height="512"');
    expect(parsed(tinted).getElementsByTagName("parsererror")).toHaveLength(0);
  });

  it("keeps a size or fill the symbol already has", () => {
    const tinted = tint('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="red"><path d="M0 0"/></svg>', "#fff");
    expect(tinted).toContain('width="20"');
    expect(tinted).not.toContain("512");
    expect(parsed(tinted).getElementsByTagName("parsererror")).toHaveLength(0);
  });
});
