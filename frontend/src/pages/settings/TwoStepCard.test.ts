import { describe, expect, it } from "vitest";
import { spaced } from "./TwoStepCard";

describe("an authenticator app's key, as shown to type in", () => {
  it("comes in fours", () => {
    expect(spaced("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")).toBe("ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567");
    expect(spaced("ABCDEF")).toBe("ABCD EF");
  });
});
