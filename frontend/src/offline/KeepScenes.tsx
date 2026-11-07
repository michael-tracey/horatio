import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { Button, ErrorText } from "../components/ui";
import { useDates } from "../dates";
import { useMe } from "../hooks";
import { manualLink } from "../manualLink";
import { isNoAnswer, useOnline } from "./connection";
import { tapsWaiting } from "./keep";
import { useKeepChoice } from "./Offline";
import { keepScenes, keptScenesSummary, keptVersion, removeScenes, subscribe, type KeptScenesSummary } from "./store";

/** A troupe's scenes kept on this device, kept up to date as that changes. */
export function useKeptScenes(troupeId: string): KeptScenesSummary | null {
  useSyncExternalStore(subscribe, keptVersion);
  return keptScenesSummary(troupeId);
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "3 scenes, 14 NPCs, 2 PCs". */
export function keptText(kept: Pick<KeptScenesSummary, "sceneIds" | "npcs" | "pcs">): string {
  return [plural(kept.sceneIds.length, "scene"), plural(kept.npcs, "NPC"), ...(kept.pcs ? [plural(kept.pcs, "PC")] : [])].join(", ");
}

/**
 * On a troupe's Scenes page, for its running staff (#503): keep its scenes on this
 * phone for a game with no signal, then when they were kept, with Update and Remove.
 * It needs "Keep my characters on this device", which says the phone is theirs.
 */
export function KeepScenes({ troupeId }: { troupeId: string }) {
  const me = useMe();
  const id = me.data?.id ?? "";
  const on = useKeepChoice(id) === "on";
  const kept = useKeptScenes(troupeId);
  const online = useOnline();
  const dates = useDates();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(isNoAnswer(e) ? new Error("Needs a connection.") : e);
    } finally {
      setBusy(false);
    }
  };
  const keep = () => void act(() => keepScenes(client, id, troupeId));

  return (
    <section aria-label="Kept on this phone" className="flex flex-col gap-2 rounded-lg border border-ash bg-dusk px-3 py-2.5 text-sm">
      {!on ? (
        <>
          <Button variant="secondary" disabled className="self-start">
            Keep tonight's scenes on this phone
          </Button>
          <p className="text-xs text-mist">
            Keeping scenes needs{" "}
            <Link to="/account/device" className="text-gold underline hover:text-parchment">
              Keep my characters on this device
            </Link>{" "}
            turned on, which says this phone is yours.
          </p>
        </>
      ) : kept ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            Kept {dates.time(new Date(kept.keptAt))} · {keptText(kept)}
          </span>
          <span className="flex gap-1">
            <Button variant="secondary" disabled={busy || !online} onClick={keep}>
              Update
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => void act(() => removeScenes(id, troupeId))}>
              Remove
            </Button>
          </span>
        </div>
      ) : (
        <>
          <Button variant="secondary" disabled={busy || !online} className="self-start" onClick={keep}>
            {busy ? "Keeping the scenes…" : "Keep tonight's scenes on this phone"}
          </Button>
          <p className="text-xs text-mist">
            Every scene of the troupe, its NPCs, PCs and stat blocks, so a fight can be run with no signal. Taps wait on the phone and go when it returns.{" "}
            <Link to={manualLink("running-a-troupe", "scenes-at-a-game-with-no-signal")} className="underline hover:text-parchment">
              How it works
            </Link>
          </p>
        </>
      )}
      <ErrorText error={error} />
    </section>
  );
}

/** How many taps wait on this device, counted again every few seconds (the cards keep their own). */
function useTapsWaiting(active: boolean): number {
  const [count, setCount] = useState(() => tapsWaiting());
  useEffect(() => {
    if (!active) return;
    setCount(tapsWaiting());
    const timer = window.setInterval(() => setCount(tapsWaiting()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return count;
}

/** Offline, on the Scenes page and a scene: how old the kept scenes are and how many taps wait. */
export function ScenesStrip({ troupeId }: { troupeId: string }) {
  const online = useOnline();
  const kept = useKeptScenes(troupeId);
  const dates = useDates();
  const waiting = useTapsWaiting(!online);
  if (online) return null;
  const parts = ["Offline"];
  if (kept) parts.push(`scenes as of ${dates.time(new Date(kept.savedAt))}`);
  if (waiting) parts.push(waiting === 1 ? "1 tap waiting to send" : `${waiting} taps waiting to send`);
  return (
    <p aria-label="Connection" className="border-t border-blood/40 bg-blood/10 px-4 py-1.5 text-center text-xs text-parchment">
      {parts.join(" · ")}
    </p>
  );
}

/** What a line-up change says while offline, in place of doing it. */
export function NeedsSignal({ className = "" }: { className?: string }) {
  return <p className={`text-xs text-mist ${className}`}>Needs a connection</p>;
}
