import { describe, expect, it } from "vitest";
import { aloneNote, confirmedNow, confirmNext, confirmOutcome, reopened, spaced } from "./TwoStepCard";

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

describe("confirming it's you with Discord, with no password (#1140)", () => {
  it("comes back to the same page, saying what was being done, without what a last try said", () => {
    expect(confirmNext("/account/sign-in", "", "app")).toBe("/account/sign-in?confirming=app");
    expect(confirmNext("/two-step", "?next=%2Ftroupes&discord_confirm=cancelled&confirming=codes", "add", { name: "My phone" })).toBe("/two-step?next=%2Ftroupes&confirming=add&name=My+phone");
    expect(confirmNext("/account/sign-in", "", "replace", { passkey: "p1" })).toBe("/account/sign-in?confirming=replace&passkey=p1");
  });

  it("opens the form again, back from Discord", () => {
    const s = { passkeys: [{ id: "p1", name: "Phone", created_at: "2026-11-01T00:00:00Z", last_used_at: null, discoverable: null }] };
    expect(reopened("add", null, s)).toBe("add");
    expect(reopened("codes", null, s)).toEqual({ what: "codes" });
    expect(reopened("app", null, s)).toEqual({ what: "app" });
    expect(reopened("setup", null, s)).toEqual({ what: "setup" });
    expect(reopened("replace", "p1", s)).toEqual({ what: "replace", id: "p1", name: "Phone" });
    expect(reopened("passkey", "p1", s)).toEqual({ what: "passkey", id: "p1", name: "Phone" });
    // A passkey gone since, or anything else, opens nothing.
    expect(reopened("passkey", "gone", s)).toBeNull();
    expect(reopened("everything", null, s)).toBeNull();
    expect(reopened(null, null, s)).toBeNull();
  });

  it("says what Discord's callback said, and nothing for words it never says", () => {
    expect(confirmOutcome("confirmed")).toEqual({ ok: true, text: "Discord confirmed it's you. Go on within 5 minutes." });
    expect(confirmOutcome("other_account")?.text).toBe("That Discord account isn't the one linked to yours, so nothing was confirmed.");
    for (const said of ["cancelled", "expired", "failed", "throttled", "not_needed"]) expect(confirmOutcome(said)?.ok).toBe(false);
    expect(confirmOutcome("You were hacked: call 555-0100")).toBeNull();
    expect(confirmOutcome(null)).toBeNull();
  });

  it("is confirmed only without a password, until the time the server gave", () => {
    const now = Date.parse("2026-11-21T12:00:00Z");
    expect(confirmedNow({ has_password: false, confirmed_until: "2026-11-21T12:04:00Z" }, now)).toBe(true);
    expect(confirmedNow({ has_password: false, confirmed_until: "2026-11-21T11:59:00Z" }, now)).toBe(false);
    expect(confirmedNow({ has_password: false, confirmed_until: null }, now)).toBe(false);
    expect(confirmedNow({ has_password: true, confirmed_until: "2026-11-21T12:04:00Z" }, now)).toBe(false);
  });
});
