import { describe, expect, it } from "vitest";
import { aloneNote, spaced } from "./TwoStepCard";

describe("an authenticator app's key, as shown to type in", () => {
  it("comes in fours", () => {
    expect(spaced("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")).toBe("ABCD EFGH IJKL MNOP QRST UVWX YZ23 4567");
    expect(spaced("ABCDEF")).toBe("ABCD EF");
  });
});

describe("a passkey that may not sign in alone (#1098)", () => {
  it("says nothing of one that can", () => {
    expect(aloneNote(true)).toBeNull();
  });

  it("says plainly when it can't, or may not, and to replace it (#1110)", () => {
    expect(aloneNote(false)).toMatch(/^Signs you in only after your password/);
    expect(aloneNote(null)).toMatch(/added before passkeys could\. To be sure, replace it on the device that keeps it\.$/);
  });
});
