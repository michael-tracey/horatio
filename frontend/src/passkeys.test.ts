import { WebAuthnError } from "@simplewebauthn/browser";
import { describe, expect, it } from "vitest";
import { ApiError } from "./api/client";
import { passkeyAborted, passkeyProblem } from "./passkeys";

const notAllowed = new DOMException("The operation either timed out or was not allowed.", "NotAllowedError");

describe("a passkey that didn't sign someone in (#1098)", () => {
  it("says nothing when another request took its place", () => {
    const aborted = new WebAuthnError({ message: "aborted", code: "ERROR_CEREMONY_ABORTED", cause: new DOMException("", "AbortError") });
    expect(passkeyAborted(aborted)).toBe(true);
    expect(passkeyAborted(new WebAuthnError({ message: notAllowed.message, code: "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY", cause: notAllowed }))).toBe(false);
  });

  it("says plainly that none was given, cancelled or timed out", () => {
    const cancelled = new WebAuthnError({ message: notAllowed.message, code: "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY", cause: notAllowed });
    expect((passkeyProblem(cancelled) as Error).message).toBe("No passkey was given. Try again, or sign in with your password.");
  });

  it("passes on what the server said", () => {
    const refused = new ApiError(401, "That passkey didn't sign you in.");
    expect(passkeyProblem(refused)).toBe(refused);
  });
});
