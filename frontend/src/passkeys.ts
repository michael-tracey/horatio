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

/** What to say when a passkey wasn't replaced (#1110): that the old one, `name`, is
 * kept as it was, and why, in plain words rather than the browser's. */
export function replaceProblem(error: unknown, name: string): Error {
  const kept = `${name} is kept as it was.`;
  const code = error instanceof WebAuthnError ? error.code : undefined;
  const cause = error instanceof WebAuthnError ? (error.cause as { name?: string } | undefined)?.name : undefined;
  if (cause === "NotAllowedError") return new Error(`No new passkey was made. ${kept}`);
  if (code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED")
    return new Error(`This device already keeps a passkey for Horatio that signs you in alone. ${name} is kept as it was: remove it if you don't need it.`);
  if (code === "ERROR_AUTHENTICATOR_MISSING_DISCOVERABLE_CREDENTIAL_SUPPORT" || code === "ERROR_AUTHENTICATOR_MISSING_USER_VERIFICATION_SUPPORT")
    return new Error(`This device can't keep a passkey that signs you in alone. ${kept}`);
  return new Error(`${error instanceof Error ? error.message : String(error)} ${kept}`);
}
