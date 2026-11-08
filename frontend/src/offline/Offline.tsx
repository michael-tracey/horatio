import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import type { CharacterListOut, Me, TapIn as Tap } from "../api/types";
import { Dialog } from "../components/Dialog";
import { Button, ErrorText } from "../components/ui";
import { useDates } from "../dates";
import { useMe } from "../hooks";
import { isNoAnswer, useOnline } from "./connection";
import { dropSent, keeping, keepsQuery, markAsked, mineOf, setKeeping, setKeptFor, tapsWaiting, waitingTaps, wasAsked, type Keeping } from "./keep";
import { choicesChanged, dropRestored, forget, keptSummary, keptVersion, refresh, removeKept, save, saveScenes, scenesTouched, subscribe, type KeptSummary } from "./store";

/** This person's choice on this device, kept up to date as it changes. */
export function useKeepChoice(userId: string | undefined): Keeping | null {
  useSyncExternalStore(subscribe, keptVersion);
  return userId ? keeping(userId) : null;
}

/** What is kept here for the signed-in person, as Account › This device shows it. */
export function useKept(): KeptSummary | null {
  useSyncExternalStore(subscribe, keptVersion);
  return keptSummary();
}

/** Ask afresh at most this often on its own (Update now asks whenever pressed). */
const REFRESH_EVERY = 5 * 60_000;
let lastRefresh = 0;

/**
 * Keeps the signed-in person's characters on the device while their choice here is
 * On (#502): each answer about them is written as it arrives, and every one is
 * asked for afresh as the app opens and when the connection comes back. Mounted
 * once, in App.
 */
export function useKeptOnDevice() {
  const client = useQueryClient();
  const me = useMe();
  const id = me.data?.id;
  const on = useKeepChoice(id) === "on";
  const online = useOnline();

  // Answers restored for someone whose session has since ended leave the screen (not the device).
  useEffect(() => {
    if (me.data !== undefined) dropRestored(client, me.data?.id ?? null);
  }, [client, me.data]);

  useEffect(() => {
    if (!id) return;
    setKeptFor(on ? id : null);
    if (!on) return;
    // Each record written a second after the last answer for it, not at every one.
    const timers = new Map<string, number>();
    const later = (record: string, write: () => Promise<unknown>) => {
      window.clearTimeout(timers.get(record));
      timers.set(
        record,
        window.setTimeout(() => void write().catch(() => undefined), 1000),
      );
    };
    const unsubscribe = client.getQueryCache().subscribe((event) => {
      if (event.type !== "updated" || event.action.type !== "success") return;
      const key = event.query.queryKey;
      // A kept troupe's scenes follow what its staff see online: a new pin, a card's taps (#503).
      for (const troupeId of scenesTouched(key)) later(`scenes:${troupeId}`, () => saveScenes(client, id, troupeId));
      const list = client.getQueryData<CharacterListOut[]>(["characters"]);
      if (list && !keepsQuery(key, mineOf(list, id))) return;
      later("person", () => save(client, id));
    });
    return () => {
      unsubscribe();
      for (const timer of timers.values()) window.clearTimeout(timer);
    };
  }, [client, id, on]);

  useEffect(() => {
    if (!id || !on || !online || Date.now() - lastRefresh < REFRESH_EVERY) return;
    lastRefresh = Date.now();
    void refresh(client, id).catch(() => undefined);
  }, [client, id, on, online]);
}

/** Turn keeping on or off for a person on this device. On asks for everything at once. */
export function useSetKeeping() {
  const client = useQueryClient();
  return async (userId: string, value: Keeping) => {
    setKeeping(userId, value);
    markAsked();
    choicesChanged();
    if (value === "off") {
      await removeKept(userId);
      return;
    }
    // Ask the browser not to clear it when space runs short (Safari may still, after weeks unused).
    void navigator.storage?.persist?.().catch(() => false);
    lastRefresh = Date.now();
    await refresh(client, userId);
  };
}

/**
 * The first time someone signs in on a device, it asks once whether to keep their
 * characters on it. Until it is answered, nothing is kept; closing it asks again
 * next time the app opens.
 */
export function KeepQuestion() {
  const me = useMe();
  const set = useSetKeeping();
  useSyncExternalStore(subscribe, keptVersion);
  const [later, setLater] = useState(false);
  const id = me.data?.id;
  const open = !!id && !later && !wasAsked() && keeping(id) === null;
  const answer = (value: Keeping) => {
    if (id) void set(id, value).catch(() => undefined);
  };
  return (
    <Dialog title="Your own phone?" open={open} onClose={() => setLater(true)}>
      <p className="text-sm">Is this your own phone? If so, Horatio can keep your characters on it so they work at games with no signal.</p>
      <p className="mt-2 text-xs text-mist">You can change this in Your account › This device.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={() => answer("on")}>Yes, keep them here</Button>
        <Button variant="secondary" onClick={() => answer("off")}>
          No, online only
        </Button>
      </div>
    </Dialog>
  );
}

function tapsText(n: number): string {
  return n === 1 ? "1 tap waiting to send" : `${n} taps waiting to send`;
}

/** A quiet line under the header while offline: how old what's shown is, and the taps waiting. */
export function OfflineStrip() {
  const online = useOnline();
  const me = useMe();
  const kept = useKept();
  const on = useKeepChoice(me.data?.id) === "on";
  const dates = useDates();
  if (online) return null;
  const parts = ["Offline"];
  if (on && kept?.refreshedAt) parts.push(`your characters as of ${dates.time(new Date(kept.refreshedAt))}`);
  const waiting = tapsWaiting();
  if (waiting) parts.push(tapsText(waiting));
  return (
    <p aria-label="Connection" className="border-b border-blood/40 bg-blood/10 px-4 py-1.5 text-center text-xs text-parchment">
      {parts.join(" · ")}
    </p>
  );
}

/**
 * Taps left waiting when the Play View closed (the session ended offline, say) go
 * once the person is signed in with a connection, from whatever screen they are on.
 * The server skips a tap it already has, so one sent twice counts once.
 */
export function useSendWaiting() {
  const me = useMe();
  const online = useOnline();
  const signedIn = !!me.data;
  useEffect(() => {
    if (!signedIn || !online) return;
    let stopped = false;
    void (async () => {
      for (const { characterId, taps } of waitingTaps()) {
        if (stopped) return;
        try {
          await unwrap(api.POST("/api/characters/{character_id}/play/taps", { params: { path: { character_id: characterId } }, body: { taps: taps as Tap[] } }));
          dropSent(characterId, taps.map((t) => t.id));
        } catch {
          // Left for the Play View, which says what went wrong.
        }
      }
    })();
    return () => {
      stopped = true;
    };
  }, [signedIn, online]);
}

/** Signing out clears what is kept here for the person, asking first if taps haven't been sent. */
export function useSignOut() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  /** Sign out at once, with no asking: the error if it failed, or null. */
  const go = async (): Promise<unknown> => {
    setBusy(true);
    setError(null);
    try {
      const id = client.getQueryData<Me | null>(["me"])?.id;
      await unwrap(api.POST("/api/auth/logout"));
      if (id) await forget(client, id);
      setAsking(0);
      navigate("/sign-in");
      return null;
    } catch (e) {
      const said = isNoAnswer(e) ? new Error("Signing out needs a connection.") : e;
      setError(said);
      return said;
    } finally {
      setBusy(false);
    }
  };
  const signOut = () => {
    const waiting = tapsWaiting();
    if (waiting) setAsking(waiting);
    else void go();
  };
  const dialog = (
    <Dialog title="Sign out?" open={asking > 0} onClose={() => setAsking(0)}>
      <p className="text-sm">{asking === 1 ? "1 tap hasn't been sent yet." : `${asking} taps haven't been sent yet.`} Sign out anyway? They'll be lost.</p>
      <div className="mt-4 flex flex-col gap-3">
        <ErrorText error={error} />
        <div className="flex flex-wrap gap-2">
          <Button variant="danger" disabled={busy} onClick={() => void go()}>
            Sign out anyway
          </Button>
          <Button variant="secondary" onClick={() => setAsking(0)}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
  return { signOut, now: go, dialog, error: asking ? null : error };
}
