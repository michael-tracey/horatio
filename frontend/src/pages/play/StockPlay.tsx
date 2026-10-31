import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { ErrorText } from "../../components/ui";
import { usePreferences } from "../../hooks";
import { kindPages, resourceText } from "../troupe/npcKinds";
import { RulesCard, StatBlock } from "../troupe/StockNpcBuilder";
import { AwakeSwitch, BoxTracker, GameLog, HealthTracker, Notes, PastGames, ResetGame, SyncStatus, useToldTap, type KeepAwake } from "./PlayPage";
import type { Damage } from "./tracker";
import type { Play, Sync } from "./usePlay";
import { useKeepAwake } from "./wakeLock";

/**
 * A Stock NPC's Play View (MET: VTM pp. 489–490; issue #215), simpler than a
 * sheet's: its kind's resource and its health levels to tap, the book's stat
 * block and its kind's rules card, and the game's log with Undo. A Stock NPC has
 * no Willpower, so nothing else needs tracking. Taps go through the same queue
 * and endpoints as everyone's, and Reset starts the next game the same way.
 */
export function StockPlay({ characterId, play }: { characterId: string; play: Play }) {
  const [params] = useSearchParams();
  const prefs = usePreferences();
  const awake = useKeepAwake(prefs.keep_awake);
  const { view, shown, sync, accept } = play;
  // Each tap says what it did in a toast, with Undo.
  const tap = useToldTap(play);
  // Opened from a Scene view's card: the way back is to that scene.
  const scene = params.get("scene");
  const sceneTroupe = params.get("troupe");
  const back = scene && sceneTroupe ? `/play/troupes/${sceneTroupe}/scenes/${scene}` : null;
  const stock = shown?.stock;
  const builder = stock?.troupe_id ? `/troupes/${stock.troupe_id}/npcs/${characterId}` : "/";

  if (!shown || !stock) {
    return (
      <StockShell back={back} builder={builder} sync={sync} awake={awake}>
        {view.isPending ? <p className="py-8 text-center text-mist">Loading…</p> : <ErrorText error={view.error} />}
      </StockShell>
    );
  }
  const record = ({ tracker, amount, damage }: { tracker: string; amount: number; damage?: Damage }) =>
    tap({ kind: "change", tracker, amount, damage: damage ?? null });
  return (
    <StockShell back={back} builder={builder} name={shown.character_name} sync={sync} awake={awake}>
      <section className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl leading-tight">{shown.character_name}</h1>
          <p className="text-sm text-mist">
            Stock NPC · {stock.kind.name} · rating {stock.rating} · {kindPages(stock.kind)}
          </p>
        </div>
        <p className="text-right text-xs text-mist">
          NPC
          <br />
          {shown.game ? `Game ${shown.game.number}` : "First game"}
        </p>
      </section>
      <div className="grid gap-3 md:grid-cols-2">
        <BoxTracker title={shown.blood_name} tracker="blood" value={shown.blood.value} most={shown.blood.most} hint={resourceText(stock.stats.resource)} record={record} loud />
        <HealthTracker view={shown} record={record} />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <StatBlock stock={stock} />
        <RulesCard kind={stock.kind} />
      </div>
      <Notes add={(note) => tap({ kind: "note", note })} />
      <GameLog view={shown} undo={(entry) => tap({ kind: "undo", undoes: entry.id })} />
      <ResetGame view={shown} sync={sync} onReset={accept} />
      <PastGames characterId={characterId} current={shown.game?.id} />
    </StockShell>
  );
}

/** The page around it: back to the scene it was opened from, or to the NPC's builder, and whether taps are saved. */
function StockShell({ back, builder, name, sync, awake, children }: { back: string | null; builder: string; name?: string; sync: Sync; awake: KeepAwake; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          {back ? (
            <Link to={back} className="inline-flex min-h-10 items-center rounded-md border border-gold/60 px-3 text-sm text-gold hover:bg-gold/10">
              ← Back to the scene
            </Link>
          ) : (
            <Link to={builder} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
              ← {name ?? "Back"}
            </Link>
          )}
          <span className="flex items-center gap-2">
            <AwakeSwitch awake={awake} />
            <SyncStatus sync={sync} />
          </span>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-3 px-4 pt-3">{children}</main>
    </div>
  );
}
