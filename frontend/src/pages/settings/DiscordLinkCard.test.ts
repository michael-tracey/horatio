import { describe, expect, it } from "vitest";
import { outcome } from "./DiscordLinkCard";

describe("what Discord's callback said", () => {
  it("is nothing without an answer", () => {
    expect(outcome(null)).toBeNull();
  });

  it("names a link, a cancel and an account linked elsewhere in plain words", () => {
    expect(outcome("linked")).toEqual({ ok: true, text: "Your Discord account is linked." });
    expect(outcome("cancelled")?.ok).toBe(false);
    expect(outcome("taken")?.text).toBe("That Discord account is already linked to another Horatio account.");
  });

  it("passes on what Discord said went wrong", () => {
    expect(outcome("Discord did not confirm your account.")).toEqual({ ok: false, text: "Discord did not confirm your account." });
  });
});
