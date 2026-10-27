import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, unwrap } from "../../api/client";
import type { PlayView } from "../../api/types";
import { afterSending, ITEM, loadQueue, makeTap, saveQueue, withPending, type Tap } from "./tracker";

// How often to look for taps from other devices, and to retry sending.
const REFRESH = 15_000;
const RETRY = 10_000;

export type Sync = {
  online: boolean;
  /** Taps made here and not yet saved on the server. */
  waiting: number;
  sending: boolean;
  /** Taps the server refused (not a lost connection), so they were dropped. */
  error: string | null;
};

/**
 * A character's Play View with its taps: shown at once, kept on the device until
 * the server has them, and sent in the order they were made whenever there is a
 * connection. Other devices' taps arrive with each refresh.
 */
export function usePlay(characterId: string) {
  const client = useQueryClient();
  const queryKey = useMemo(() => ["play", characterId], [characterId]);
  const view = useQuery({
    queryKey,
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/play", { params: { path: { character_id: characterId } } })),
    refetchInterval: REFRESH,
    refetchOnWindowFocus: true,
  });
  const [queue, setQueue] = useState<Tap[]>(() => loadQueue(characterId));
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The last send got no good answer: wait for the next retry rather than at once.
  const [failed, setFailed] = useState(false);
  const busy = useRef(false);
  const latest = useRef(queue);
  latest.current = queue;

  useEffect(() => saveQueue(characterId, queue), [characterId, queue]);

  useEffect(() => {
    const up = () => {
      setOnline(true);
      setFailed(false);
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);

  const accept = useCallback(
    async (data: PlayView) => {
      // A refresh started before this answer would bring back the old view.
      await client.cancelQueries({ queryKey });
      client.setQueryData(queryKey, data);
    },
    [client, queryKey],
  );

  const flush = useCallback(async () => {
    const batch = latest.current;
    if (busy.current || batch.length === 0) return;
    busy.current = true;
    setSending(true);
    try {
      const data = await unwrap(
        api.POST("/api/characters/{character_id}/play/taps", { params: { path: { character_id: characterId } }, body: { taps: batch } }),
      );
      setQueue((now) => afterSending(now, batch));
      setOnline(true);
      setFailed(false);
      setError(null);
      await accept(data);
      // An item given or discarded, or brought back by Undo: the Equipment tabs ask again.
      if (batch.some((t) => t.kind === "undo" || t.tracker.startsWith(ITEM))) void client.invalidateQueries({ queryKey: ["character-equipment"] });
    } catch (e) {
      if (e instanceof ApiError && e.status < 500 && e.status !== 408 && e.status !== 429) {
        // The server will never take these; keeping them would block every later tap.
        setQueue((now) => afterSending(now, batch));
        setError(`Some taps could not be saved: ${e.message}`);
      } else {
        setFailed(true);
        if (!(e instanceof ApiError)) setOnline(false); // no answer at all: the connection is down
      }
    } finally {
      busy.current = false;
      setSending(false);
    }
  }, [accept, characterId, client]);

  // Send whenever there is something to send, and keep trying while it waits.
  useEffect(() => {
    if (queue.length === 0 || sending) return;
    if (online && !failed) void flush();
    const timer = window.setInterval(() => void flush(), RETRY);
    return () => window.clearInterval(timer);
  }, [queue, online, failed, sending, flush]);

  const tap = useCallback(
    (what: Parameters<typeof makeTap>[0]) => {
      setQueue((now) => [...now, makeTap(what, view.data?.game?.id)]);
    },
    [view.data?.game?.id],
  );

  const shown = useMemo(() => (view.data ? withPending(view.data, queue) : undefined), [view.data, queue]);
  const sync: Sync = { online, waiting: queue.length, sending, error };
  return { view, shown, tap, sync, accept };
}

/** What `usePlay` gives: a Play View, its taps and how they are syncing. */
export type Play = ReturnType<typeof usePlay>;
