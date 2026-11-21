import { WebAuthnError } from "@simplewebauthn/browser";
import { describe, expect, it } from "vitest";
import { ApiError } from "./api/client";
import { passkeyAborted, passkeyProblem, replaceProblem } from "./passkeys";

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

describe("a passkey that wasn't replaced (#1110)", () => {
  const said = (error: unknown) => replaceProblem(error, "Phone").message;

  it("says plainly that none was made, and the old one is kept", () => {
    const cancelled = new WebAuthnError({ message: notAllowed.message, code: "ERROR_PASSTHROUGH_SEE_CAUSE_PROPERTY", cause: notAllowed });
    expect(said(cancelled)).toBe("No new passkey was made. Phone is kept as it was.");
  });

  it("says when the device has one that signs in alone already, or can't keep one", () => {
    const there = new WebAuthnError({ message: "previously registered", code: "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED", cause: new DOMException("", "InvalidStateError") });
    expect(said(there)).toBe("This device already keeps a passkey for Horatio that signs you in alone. Phone is kept as it was: remove it if you don't need it.");
    const cannot = new WebAuthnError({ message: "no support", code: "ERROR_AUTHENTICATOR_MISSING_DISCOVERABLE_CREDENTIAL_SUPPORT", cause: new DOMException("", "ConstraintError") });
    expect(said(cannot)).toBe("This device can't keep a passkey that signs you in alone. Phone is kept as it was.");
  });

  it("passes on what the server said, with the old one kept", () => {
    expect(said(new ApiError(422, "This device can't keep a passkey that signs you in alone."))).toBe("This device can't keep a passkey that signs you in alone. Phone is kept as it was.");
  });
});
