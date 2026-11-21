import { WebAuthnError } from "@simplewebauthn/browser";

/** A passkey request that another took the place of, or that the page stopped as it
 * left: nothing to tell anyone. */
export function passkeyAborted(error: unknown): boolean {
  return error instanceof WebAuthnError && error.code === "ERROR_CEREMONY_ABORTED";
}

/** What to say when a passkey didn't sign someone in. The browser's own words for one
 * not given, cancelled or timed out, say little to most people. */
export function passkeyProblem(error: unknown): unknown {
  const cause = error instanceof WebAuthnError ? (error.cause as { name?: string } | undefined) : undefined;
  return cause?.name === "NotAllowedError" ? new Error("No passkey was given. Try again, or sign in with your password.") : error;
}
