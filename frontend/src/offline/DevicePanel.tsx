import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Link } from "react-router";
import { Button, Card, ErrorText } from "../components/ui";
import { useDates } from "../dates";
import { useMe } from "../hooks";
import { manualLink } from "../manualLink";
import { Setting } from "../pages/settings/SettingsPage";
import { isNoAnswer, useOnline } from "./connection";
import { useKeepChoice, useKept, useSetKeeping } from "./Offline";
import { keptText } from "./KeepScenes";
import { keptScenesSummaries, keptVersion, loadSummary, refresh, removeKept, removeScenes, subscribe } from "./store";

function useKeptScenesList() {
  useSyncExternalStore(subscribe, keptVersion);
  return keptScenesSummaries();
}

/** "120 KB", "1.4 MB". */
export function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Account › This device (#502): whether this person's characters are kept here for
 * games with no signal, what is kept now, and Update now and Remove.
 */
export function DevicePanel() {
  const me = useMe();
  const id = me.data?.id ?? "";
  const choice = useKeepChoice(id);
  const on = choice === "on";
  const kept = useKept();
  // A troupe's scenes, kept by its running staff from its Scenes page (#503).
  const scenes = useKeptScenesList();
  const online = useOnline();
  const dates = useDates();
  const client = useQueryClient();
  const set = useSetKeeping();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (id) void loadSummary(id);
  }, [id]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(isNoAnswer(e) ? new Error("Updating needs a connection.") : e);
    } finally {
      setBusy(false);
    }
  };

  const options: [boolean, string][] = [
    [false, "Off: online only"],
    [true, "On: my characters work offline"],
  ];
  return (
    <Card
      title="This device"
      actions={
        <Link to={manualLink("players", "using-horatio-at-a-game-with-no-signal")} className="text-sm text-gold underline hover:text-parchment">
          At a game with no signal
        </Link>
      }
    >
      <Setting
        label="Keep my characters on this device"
        hint={
          on
            ? "Your characters' sheets, Play Views and powers are kept here, so they work without signal. Staff screens always need a connection."
            : "Nothing is kept here. For a borrowed or shared phone."
        }
      >
        <span role="radiogroup" aria-label="Keep my characters on this device" className="inline-flex overflow-hidden rounded-md border border-ash">
          {options.map(([value, text]) => (
            <button
              key={text}
              type="button"
              role="radio"
              aria-checked={on === value}
              disabled={busy}
              onClick={() => on !== value && void act(() => set(id, value ? "on" : "off"))}
              className={`min-h-9 px-3 text-sm ${on === value ? "bg-gold/20 text-gold" : "text-mist hover:text-parchment"} [&+&]:border-l [&+&]:border-ash`}
            >
              {text}
            </button>
          ))}
        </span>
      </Setting>
      {on && (
        <div className="flex flex-col gap-3 pt-3">
          {kept && kept.characters.length > 0 ? (
            <div role="group" aria-label="Kept on this device" className="text-sm">
              <p className="text-parchment">Kept here now: {kept.characters.map((c) => c.name).join(", ")}</p>
              <p className="text-xs text-mist">
                {kept.refreshedAt ? `Updated ${dates.dateTime(new Date(kept.refreshedAt))}` : "Not updated yet"} · about {sizeText(kept.bytes)}
              </p>
            </div>
          ) : (
            <p className="text-sm text-mist">{busy ? "Keeping your characters…" : "Nothing is kept here yet. Update now keeps your characters in play."}</p>
          )}
          {scenes.map((k) => (
            <div key={k.troupeId} role="group" aria-label={`Scenes of ${k.troupeName}`} className="flex flex-wrap items-center justify-between gap-2 border-t border-ash/60 pt-3 text-sm">
              <span>
                <span className="block text-parchment">Scenes of {k.troupeName}</span>
                <span className="block text-xs text-mist">
                  Kept {dates.dateTime(new Date(k.keptAt))} · {keptText(k)} · about {sizeText(k.bytes)}
                </span>
              </span>
              <Button variant="ghost" disabled={busy} aria-label={`Remove the scenes of ${k.troupeName}`} onClick={() => void act(() => removeScenes(id, k.troupeId))}>
                Remove
              </Button>
            </div>
          ))}
          <ErrorText error={error} />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={busy || !online} onClick={() => void act(() => refresh(client, id))}>
              Update now
            </Button>
            <Button variant="danger" disabled={busy} onClick={() => void act(() => removeKept(id))}>
              Remove from this device
            </Button>
          </div>
          {!online && <p className="text-xs text-mist">Updating needs a connection.</p>}
        </div>
      )}
    </Card>
  );
}
