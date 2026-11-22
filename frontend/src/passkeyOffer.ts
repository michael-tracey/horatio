/**
 * The offer of a passkey after a password sign-in (#1193): once on each device, kept in
 * its browser storage. A password sign-in marks this tab (sessionStorage), so the offer
 * follows that sign-in only; choosing to add one, or not now, marks the device
 * (localStorage), so it isn't offered there again. Storage that can't be used, as in
 * some private windows, offers nothing.
 */

const SIGNED_IN = "horatio.passwordSignIn";
const OFFERED = "horatio.passkeyOffered";

type Storages = { session?: Storage; local?: Storage };

function storages(given?: Storages): Storages {
  if (given) return given;
  try {
    return { session: globalThis.sessionStorage, local: globalThis.localStorage };
  } catch {
    return {};
  }
}

/** This tab has just signed in with a password. */
export function markPasswordSignIn(given?: Storages): void {
  try {
    storages(given).session?.setItem(SIGNED_IN, "1");
  } catch {
    // Nothing kept: nothing offered.
  }
}

/** This tab signed in another way, as with a passkey: no offer. */
export function forgetPasswordSignIn(given?: Storages): void {
  try {
    storages(given).session?.removeItem(SIGNED_IN);
  } catch {
    // Nothing to forget.
  }
}

/** Whether to offer a passkey now: after a password sign-in in this tab, on a device
 * not offered one before. */
export function offerDue(given?: Storages): boolean {
  try {
    const { session, local } = storages(given);
    return session?.getItem(SIGNED_IN) === "1" && local?.getItem(OFFERED) === null;
  } catch {
    return false;
  }
}

/** The offer was answered, either way: not again on this device. */
export function offerAnswered(given?: Storages): void {
  try {
    const { session, local } = storages(given);
    local?.setItem(OFFERED, "1");
    session?.removeItem(SIGNED_IN);
  } catch {
    // Not kept: it may be offered again after the next password sign-in.
  }
}
