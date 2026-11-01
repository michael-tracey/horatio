import { describe, expect, it } from "vitest";
import { safeNext, withNext } from "./next";

describe("safeNext", () => {
  it("keeps a path on this site, with its query and fragment", () => {
    expect(safeNext("/cycles/abc")).toBe("/cycles/abc");
    expect(safeNext("/troupes/abc/players?show=all#top")).toBe("/troupes/abc/players?show=all#top");
    expect(safeNext("/")).toBe("/");
  });

  it("refuses nothing at all", () => {
    expect(safeNext(null)).toBeNull();
    expect(safeNext(undefined)).toBeNull();
    expect(safeNext("")).toBeNull();
  });

  it("refuses another site, however it is written", () => {
    for (const raw of [
      "https://evil.example",
      "http://evil.example/cycles/abc",
      "//evil.example",
      "///evil.example",
      "/\\evil.example",
      "\\\\evil.example",
      "\\/evil.example",
      "javascript:alert(1)",
      "data:text/html,hi",
      "evil.example",
      "cycles/abc",
    ]) {
      expect(safeNext(raw), raw).toBeNull();
    }
  });

  it("refuses encoded and hidden tricks", () => {
    for (const raw of [
      "/%2F/evil.example",
      "/%2fevil.example",
      "/%5Cevil.example",
      "/%5cevil.example",
      "/\t/evil.example",
      "/\n/evil.example",
      "/ /evil.example",
      "/%09/evil.example",
      "/%E0%A4%A",
    ]) {
      expect(safeNext(raw), raw).toBeNull();
    }
  });

  it("refuses the sign-in pages, so nothing goes round in a circle", () => {
    expect(safeNext("/sign-in")).toBeNull();
    expect(safeNext("/sign-up?next=/cycles/abc")).toBeNull();
    expect(safeNext("/sign-ins-are-fine-elsewhere")).toBe("/sign-ins-are-fine-elsewhere");
  });

  it("refuses something too long to be a link", () => {
    expect(safeNext(`/${"a".repeat(2001)}`)).toBeNull();
  });
});

describe("withNext", () => {
  it("adds a safe next, encoded", () => {
    expect(withNext("/sign-up", "/troupes/abc")).toBe("/sign-up?next=%2Ftroupes%2Fabc");
    expect(withNext("/sign-in", "/cycles/abc?tab=1")).toBe("/sign-in?next=%2Fcycles%2Fabc%3Ftab%3D1");
  });

  it("leaves an unsafe or missing one off", () => {
    expect(withNext("/sign-in", "//evil.example")).toBe("/sign-in");
    expect(withNext("/sign-in", null)).toBe("/sign-in");
  });
});
