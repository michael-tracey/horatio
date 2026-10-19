import { describe, expect, it } from "vitest";
import { fileSize } from "./BackupsTab";

describe("fileSize", () => {
  it("picks a unit", () => {
    expect(fileSize(512)).toBe("512 B");
    expect(fileSize(20_480)).toBe("20 KB");
    expect(fileSize(2_516_582)).toBe("2.4 MB");
  });
});
