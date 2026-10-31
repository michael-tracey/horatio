import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, SceneOut, TestPool } from "../../api/types";
import { LinesVeilsNote } from "../../components/LinesVeils";
import { Button, ErrorText, Input } from "../../components/ui";
import { usePreferences } from "../../hooks";
import { LogEntries, ResetGame, SyncStatus } from "./PlayPage";
import { EquipmentSwitches } from "./EquipmentSwitches";
import { equipmentModifiers } from "./equipped";
import { ModifiersPanel } from "./Modifiers";
import { attackGlance, defenceGlance, fightFirst, grouped, topAttacks, type Modifier } from "./pools";
import { PowersList } from "./Powers";
import { formsOn, healthMost } from "./powers";
import { PoolRow } from "./ReferenceTabs";
import { findPins, loadOpen, saveOpen, toggleOpen, unpin, type Section } from "./scene";
import { RenameScene, SCENE_REFRESH, useSceneChanges } from "./ScenesPage";
import { incapacitated, latestUndoable, type Damage, type Shown } from "./tracker";
import { useModifiers } from "./useModifiers";
import { usePlay } from "./usePlay";
import { useReference } from "./useReference";
import { useKeepAwake } from "./wakeLock";
import { expandPower } from "../troupe/stockNpcs";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * One of a troupe's scenes: several of its characters on a page, side by side,
 * for the staff running it. Each card is a character's Play View in small: Blood,
 * Willpower, health and Beast traits to tap, Undo and the game's log, and a way
 * into the full Play View. Taps go through the same code and endpoints as the full
 * one, so the two always agree. Who is pinned is kept on the server, so every
 * storyteller with the scene open sees the same characters (issue #231).
 */
export function ScenePage() {
  const { troupeId = "", sceneId = "" } = useParams();
  const prefs = usePreferences();
  // As the Play View's switch on this device says, or the settings.
  const awake = useKeepAwake(prefs.keep_awake).held;
  const client = useQueryClient();
  const sceneKey = ["scene", sceneId];
  const scene = useQuery({
    queryKey: sceneKey,
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/scenes/{scene_id}", { params: { path: { troupe_id: troupeId, scene_id: sceneId } } })),
    // Pins another storyteller makes show here, as their taps do on each card.
    refetchInterval: SCENE_REFRESH,
    refetchOnWindowFocus: true,
  });
  // Unpinning shows at once, and the server's answer settles it.
  const pinning = useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => {
      const where = { params: { path: { troupe_id: troupeId, scene_id: sceneId, character_id: id } } };
      return unwrap(on ? api.PUT("/api/troupes/{troupe_id}/scenes/{scene_id}/characters/{character_id}", where) : api.DELETE("/api/troupes/{troupe_id}/scenes/{scene_id}/characters/{character_id}", where));
    },
    // A pin waits for the server, which says whether it is a Stock NPC, whose card is its own.
    onMutate: async ({ id, on }) => {
      if (on) return;
      await client.cancelQueries({ queryKey: sceneKey });
      client.setQueryData<SceneOut>(sceneKey, (now) => now && { ...now, characters: unpin(now.characters, id) });
    },
    onSuccess: (data) => client.setQueryData(sceneKey, data),
    onError: () => client.invalidateQueries({ queryKey: sceneKey }),
    onSettled: () => client.invalidateQueries({ queryKey: ["scenes", troupeId] }),
  });
  const changes = useSceneChanges(troupeId);
  const [renaming, setRenaming] = useState(false);

  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  // The same query as the troupe's Characters tab, for the search.
  const roster = useQuery({
    queryKey: ["roster", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", { params: { path: { troupe_id: troupeId } } })),
  });
  const pinned = scene.data?.characters ?? [];
  const stock = new Map((scene.data?.stock ?? []).map((s) => [s.character_id, s]));
  const list = `/play/troupes/${troupeId}/scenes`;
  // Full view comes back here.
  const back = `?troupe=${troupeId}&scene=${sceneId}`;

  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2">
          <Link to={list} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
            ← Scenes{troupe.data ? ` of ${troupe.data.name}` : ""}
          </Link>
          {awake && (
            <span className="rounded-full border border-ash px-2.5 py-0.5 text-xs whitespace-nowrap text-mist" title="Kept on while the Scene view is open, as your settings ask.">
              ☀ Screen awake
            </span>
          )}
        </div>
      </header>
      <main className="mx-auto flex max-w-6xl flex-col gap-3 px-4 pt-3">
        {!scene.data ? (
          scene.isPending ? (
            <p className="py-8 text-center text-mist">Loading…</p>
          ) : (
            <>
              <ErrorText error={scene.error} />
              <Link to={list} className="text-sm text-mist underline hover:text-parchment">
                Back to the troupe's scenes
              </Link>
            </>
          )
        ) : (
          <>
            {renaming ? (
              <RenameScene
                name={scene.data.name}
                pending={changes.rename.isPending}
                onSave={async (name) => {
                  await changes.rename.mutateAsync({ id: sceneId, name });
                  setRenaming(false);
                }}
                onCancel={() => setRenaming(false)}
                className="max-w-md"
              />
            ) : (
              <div className="flex flex-wrap items-baseline gap-x-3">
                <h1 className="text-xl text-gold">{scene.data.name}</h1>
                <span className="text-xs text-mist">{scene.data.mine ? "Your scene" : `${scene.data.created_by_name}'s scene`}</span>
                {scene.data.can_change && (
                  <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => setRenaming(true)}>
                    Rename
                  </button>
                )}
              </div>
            )}
            <ErrorText error={changes.rename.error} />
            <AddToScene roster={roster.data ?? []} pinned={pinned} onPin={(id) => pinning.mutate({ id, on: true })} error={roster.error ?? pinning.error} />
            {pinned.length === 0 ? (
              <p className="py-8 text-center text-mist">Nobody is in the scene yet. Find an NPC above to put them here.</p>
            ) : (
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {pinned.map((id) => {
                  const remove = () => pinning.mutate({ id, on: false });
                  const stocked = stock.get(id);
                  return (
                    <li key={id} className="min-w-0">
                      {stocked ? <StockCard pin={stocked} back={back} onRemove={remove} /> : <SceneCard characterId={id} back={back} onRemove={remove} />}
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="text-xs text-mist">
              The scene is kept for the troupe: the other staff running it see who is in it, and can open it themselves. To put everyone back for the next game, use{" "}
              <Link to={`/troupes/${troupeId}/play`} className="underline hover:text-parchment">
                At game
              </Link>
              , or reset one character on their card.
            </p>
          </>
        )}
      </main>
    </div>
  );
}

/** A search over the troupe's characters, NPCs first, that pins the one picked. */
function AddToScene({ roster, pinned, onPin, error }: { roster: RosterEntry[]; pinned: string[]; onPin: (id: string) => void; error: unknown }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const found = findPins(
    roster.filter((c) => !pinned.includes(c.character_id)),
    text,
  )
    .sort((a, b) => Number(b.kind === "npc") - Number(a.kind === "npc"))
    .slice(0, 12);
  const pick = (id: string) => {
    onPin(id);
    setText("");
  };
  return (
    <div className="relative max-w-md">
      <label className="flex flex-col gap-1 text-sm">
        Add to the scene
        <Input
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder="Find an NPC or character by name"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setOpen(true)}
          // Late enough that a click on the list lands first.
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && found[0]) {
              e.preventDefault();
              pick(found[0].character_id);
            } else if (e.key === "Escape") setOpen(false);
          }}
        />
      </label>
      {open && (
        <div onMouseDown={(e) => e.preventDefault()} className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-ash bg-dusk py-1 shadow-lg">
          <ul role="listbox" aria-label="Characters">
            {found.map((c) => (
              <li
                key={c.character_id}
                role="option"
                aria-selected={false}
                onClick={() => pick(c.character_id)}
                className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm hover:bg-night"
              >
                <span className="min-w-0 flex-1 truncate">{c.character_name}</span>
                <span className="shrink-0 text-xs text-mist">{c.kind === "npc" ? "NPC" : c.player_name}</span>
              </li>
            ))}
          </ul>
          {found.length === 0 && <p className="px-3 py-2 text-sm text-mist">{roster.length === 0 ? "No characters in the troupe yet." : "Nobody else matches."}</p>}
        </div>
      )}
      <ErrorText error={error} />
    </div>
  );
}

/** A small round button for one thumb. */
function Step({ label, onClick, disabled, tone = "plain", children }: { label: string; onClick: () => void; disabled?: boolean; tone?: "plain" | "blood"; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "grid h-10 min-w-10 place-items-center rounded-full border px-2 text-lg font-semibold transition-colors active:scale-95 tap-off",
        tone === "blood" ? "border-blood bg-blood text-parchment hover:bg-blood-bright" : "border-line bg-night text-parchment hover:border-mist",
      )}
    >
      {children}
    </button>
  );
}

/** One counter in a row: its name, small boxes filled to its value, and the buttons. */
function Counter({
  title,
  value,
  most,
  fill,
  spendIsUp,
  onChange,
}: {
  title: string;
  value: number;
  most: number;
  fill: string;
  /** Beast traits are gained rather than spent: "+" adds one. */
  spendIsUp?: boolean;
  onChange: (amount: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline justify-between text-sm">
          <span className="text-gold">{title}</span>
          <span className="font-display text-lg" aria-label={`${title}: ${value} of ${most}`}>
            {value}
            <span className="text-sm text-mist"> / {most}</span>
          </span>
        </p>
        <div className="mt-1 flex flex-wrap gap-1" aria-hidden="true">
          {Array.from({ length: most }, (_, i) => (
            <span key={i} className={cx("h-2.5 w-2.5 rounded-sm border", i < value ? fill : "border-line bg-night")} />
          ))}
        </div>
      </div>
      <Step label={spendIsUp ? `Remove a ${title} point` : `Spend ${title}`} onClick={() => onChange(-1)} disabled={value <= 0} tone={spendIsUp ? "plain" : "blood"}>
        −
      </Step>
      <Step label={spendIsUp ? `Gain a ${title} point` : `Restore ${title}`} onClick={() => onChange(1)} disabled={value >= most} tone={spendIsUp ? "blood" : "plain"}>
        +
      </Step>
    </div>
  );
}

function HealthRow({ view, damage }: { view: Shown; damage: (kind: Damage, amount: number) => void }) {
  const marks = view.health.marks;
  const total = healthMost(view);
  const has = (kind: Damage) => marks.includes(kind);
  return (
    <div>
      <p className="flex items-baseline justify-between text-sm">
        <span className="text-gold">Health</span>
        <span className="font-display text-lg" aria-label={`Health: ${marks.length} of ${total} marked`}>
          {marks.length}
          <span className="text-sm text-mist"> / {total} marked</span>
        </span>
      </p>
      <div className="mt-1 flex flex-wrap gap-1" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => {
          const mark = marks[i];
          return (
            <span
              key={i}
              className={cx(
                "h-2.5 w-2.5 rounded-sm border",
                mark === "aggravated" ? "border-blood bg-blood" : mark === "normal" ? "border-mist bg-mist" : "border-line bg-night",
              )}
            />
          );
        })}
      </div>
      {incapacitated(view) && <p className="mt-1 text-xs text-blood-bright">Incapacitated</p>}
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        <Button variant="danger" className="min-h-10 px-2" disabled={marks.length >= total} onClick={() => damage("normal", 1)}>
          + Normal
        </Button>
        <Button variant="danger" className="min-h-10 px-2" disabled={marks.length >= total} onClick={() => damage("aggravated", 1)}>
          + Aggravated
        </Button>
        <Button variant="secondary" className="min-h-10 px-2" disabled={!has("normal")} onClick={() => damage("normal", -1)}>
          Heal normal
        </Button>
        <Button variant="secondary" className="min-h-10 px-2" disabled={!has("aggravated")} onClick={() => damage("aggravated", -1)}>
          Heal aggravated
        </Button>
      </div>
    </div>
  );
}

const SECTIONS = [
  ["pools", "Pools"],
  ["powers", "Powers"],
  ["log", "Log"],
  ["reset", "Reset"],
] as const;

/** The top three attacks and the defences, a line each, as the Pools tab works them out. */
function PoolsGlance({ pools, willpower, modifiers, on }: { pools: TestPool[]; willpower: number; modifiers: Modifier[]; on: string[] }) {
  const attacks = topAttacks(pools, willpower, modifiers, on).map((p) => attackGlance(p, willpower, modifiers, on));
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      <p>
        <span className="text-gold">Attack </span>
        {attacks.length > 0 ? attacks.join(" · ") : <span className="text-mist">none</span>}
      </p>
      <p>
        <span className="text-gold">Defence </span>
        {defenceGlance(pools, willpower, modifiers, on).join(" · ")}
      </p>
    </div>
  );
}

/**
 * A Stock NPC in the scene (issue #215): its name, kind and rating, its test pool
 * and specializations at a glance, and its kind's resource and health levels to
 * tap. It has the same `usePlay` as its full Play View, the Stock one, so its taps,
 * Undo and log are everyone's.
 */
function StockCard({ pin, back, onRemove }: { pin: SceneOut["stock"][number]; back: string; onRemove: () => void }) {
  const characterId = pin.character_id;
  const { view, shown, tap, sync, accept } = usePlay(characterId);
  const [open, setOpen] = useState(() => loadOpen(characterId));
  useEffect(() => saveOpen(characterId, open), [characterId, open]);
  const toggle = (next: Section) => setOpen((now) => toggleOpen(now, next));
  const stock = shown?.stock;

  if (!shown || !stock) {
    return (
      <article className="flex flex-col gap-2 rounded-lg border border-ash bg-dusk p-3" aria-label={pin.name}>
        <h2 className="truncate text-lg leading-tight text-gold">{pin.name}</h2>
        {view.isPending ? <p className="text-mist">Loading…</p> : <ErrorText error={view.error} />}
        <Button variant="secondary" className="self-start" onClick={onRemove}>
          Remove from the scene
        </Button>
      </article>
    );
  }
  const change = (tracker: string, amount: number, damage?: Damage) => tap({ kind: "change", tracker, amount, damage: damage ?? null });
  const last = latestUndoable(shown.log);
  const name = shown.character_name;
  const stats = stock.stats;
  const specializations = [...stats.skill_pools.map((p) => `${p.name} ${p.pool}`), ...stats.powers.map((p) => expandPower(p.name, p.dots))];
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-ash bg-dusk p-3" aria-label={name}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-lg leading-tight text-gold">{name}</h2>
          <p className="text-xs text-mist">
            Stock NPC · {stock.kind.name} · rating {stock.rating}
          </p>
        </div>
        <SyncStatus sync={sync} />
      </header>
      <Counter title={shown.blood_name} value={shown.blood.value} most={shown.blood.most} fill="border-blood bg-blood" onChange={(n) => change("blood", n)} />
      <HealthRow view={shown} damage={(kind, amount) => change("health", amount, kind)} />
      <div className="flex flex-col gap-0.5 text-sm">
        <p>
          <span className="text-gold">Test pool </span>
          {stats.pool} in most challenges
        </p>
        <p>
          <span className="text-gold">Specializations </span>
          {specializations.length > 0 ? specializations.join(" · ") : <span className="text-mist">none</span>}
        </p>
        <p className="text-xs text-mist">No Willpower: no retests unless it overbids</p>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-t border-ash pt-2">
        <Button variant="secondary" className="min-h-10 px-3" disabled={!last} aria-label={last ? `Undo ${last.text}` : "Undo"} onClick={() => last && tap({ kind: "undo", undoes: last.id })}>
          Undo
        </Button>
        {SECTIONS.filter(([section]) => section === "log" || section === "reset").map(([section, label]) => (
          <Button key={section} variant="ghost" className="min-h-10 px-3" aria-expanded={open.includes(section)} onClick={() => toggle(section)}>
            {label} {open.includes(section) ? "▴" : "▾"}
          </Button>
        ))}
        <Link to={`/play/characters/${characterId}${back}`} className="ml-auto inline-flex min-h-10 items-center text-sm text-mist underline hover:text-parchment" aria-label={`Open the full Play View of ${name}`}>
          Full view
        </Link>
      </div>
      {open.includes("log") && (
        <div className="max-h-56 overflow-y-auto">
          <LogEntries log={shown.log} />
        </div>
      )}
      {open.includes("reset") && <ResetGame view={shown} sync={sync} onReset={accept} />}
      <ErrorText error={view.error} />
      <button type="button" className="self-start text-xs text-mist underline hover:text-parchment" onClick={onRemove} aria-label={`Remove ${name} from the scene`}>
        Remove from the scene
      </button>
    </article>
  );
}

/**
 * One character in the scene: the same `usePlay` as the full Play View (so its
 * one query, its refresh and its queue of unsent taps are the same), with the
 * trackers a scene needs.
 */
function SceneCard({ characterId, back, onRemove }: { characterId: string; back: string; onRemove: () => void }) {
  const { view, shown, tap, sync, accept } = usePlay(characterId);
  const { reference } = useReference(characterId);
  const modifiers = useModifiers(characterId);
  // Which sections are open is kept on this device, per card: it is about one screen.
  const [open, setOpen] = useState(() => loadOpen(characterId));
  useEffect(() => saveOpen(characterId, open), [characterId, open]);
  const toggle = (next: Section) => setOpen((now) => toggleOpen(now, next));

  if (!shown) {
    return (
      <article className="flex flex-col gap-2 rounded-lg border border-ash bg-dusk p-3" aria-label="Character in the scene">
        {view.isPending ? <p className="text-mist">Loading…</p> : <ErrorText error={view.error} />}
        <Button variant="secondary" className="self-start" onClick={onRemove}>
          Remove from the scene
        </Button>
      </article>
    );
  }
  const change = (tracker: string, amount: number, damage?: Damage) => tap({ kind: "change", tracker, amount, damage: damage ?? null });
  const last = latestUndoable(shown.log);
  const name = shown.character_name;
  const on = shown.powers.filter((p) => p.on).map((p) => p.key);
  const willpower = shown.willpower.value;
  // The player's own modifiers, then what the items equipped make (issue #306).
  const counting = [...modifiers.modifiers, ...equipmentModifiers(shown.equipment, shown.equipped)];
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-ash bg-dusk p-3" aria-label={name}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-lg leading-tight text-gold">{name}</h2>
          <p className="text-xs text-mist">
            {shown.kind === "npc" ? "NPC" : shown.player_name}
            {shown.clan ? ` · ${shown.clan}` : ""}
          </p>
          <LinesVeilsNote value={reference?.lines_veils} who={shown.player_name} />
          {/* The form they are in (issue #200), switched on the full Play View. */}
          {formsOn(shown).map((f) => (
            <span key={f.key} className="mt-1 inline-block rounded-full border border-gold/60 bg-gold/10 px-2 py-0.5 text-xs text-gold" title={f.notes.join(" ")}>
              {f.name}
            </span>
          ))}
        </div>
        <SyncStatus sync={sync} />
      </header>
      {/* A ghoul's spendable Blood is its vitae; the human Blood beside it can't be spent. */}
      <Counter title={shown.vitae ? "Vitae" : "Blood"} value={shown.blood.value} most={shown.blood.most} fill="border-blood bg-blood" onChange={(n) => change("blood", n)} />
      {shown.vitae && <p className="-mt-2 text-xs text-mist">{shown.vitae.human} human Blood, which can't be spent</p>}
      <Counter title="Willpower" value={shown.willpower.value} most={shown.willpower.most} fill="border-gold/70 bg-gold/70" onChange={(n) => change("willpower", n)} />
      <HealthRow view={shown} damage={(kind, amount) => change("health", amount, kind)} />
      {reference && <PoolsGlance pools={reference.pools} willpower={willpower} modifiers={counting} on={on} />}
      {shown.panels.beast && <Counter title="Beast traits" value={shown.beast.value} most={shown.beast.most} fill="border-gold/70 bg-gold/70" spendIsUp onChange={(n) => change("beast", n)} />}
      <div className="flex flex-wrap items-center gap-1.5 border-t border-ash pt-2">
        <Button
          variant="secondary"
          className="min-h-10 px-3"
          // An influence spend is undone on the full Play View, which checks with the staff who changed it.
          disabled={!last || !!last.influence}
          aria-label={last ? `Undo ${last.text}` : "Undo"}
          onClick={() => last && tap({ kind: "undo", undoes: last.id })}
        >
          Undo
        </Button>
        {SECTIONS.map(([section, label]) => (
          <Button key={section} variant="ghost" className="min-h-10 px-3" aria-expanded={open.includes(section)} onClick={() => toggle(section)}>
            {label} {open.includes(section) ? "▴" : "▾"}
          </Button>
        ))}
        <Link to={`/play/characters/${characterId}${back}`} className="ml-auto inline-flex min-h-10 items-center text-sm text-mist underline hover:text-parchment" aria-label={`Open the full Play View of ${name}`}>
          Full view
        </Link>
      </div>
      {open.includes("pools") &&
        (reference ? (
          <div className="flex max-h-96 flex-col gap-2 overflow-y-auto">
            {fightFirst(grouped(reference.pools)).map(([group, pools]) => (
              <section key={group} aria-label={group}>
                <h3 className="text-xs tracking-wide text-mist uppercase">{group}</h3>
                <ul>
                  {pools.map((p) => (
                    <PoolRow key={p.key} pool={p} willpower={willpower} modifiers={counting} on={on} />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        ) : (
          <p className="text-sm text-mist">Loading the pools…</p>
        ))}
      {open.includes("powers") && (
        <div className="flex max-h-96 flex-col gap-3 overflow-y-auto">
          <PowersList powers={shown.powers} tap={tap} />
          <EquipmentSwitches items={shown.equipment} equipped={shown.equipped} pools={reference?.pools ?? []} tap={tap} />
          <ModifiersPanel pools={reference?.pools ?? []} modifiers={modifiers} />
        </div>
      )}
      {open.includes("log") && (
        <div className="max-h-56 overflow-y-auto">
          <LogEntries log={shown.log} />
        </div>
      )}
      {open.includes("reset") && <ResetGame view={shown} sync={sync} onReset={accept} />}
      <ErrorText error={view.error} />
      <button type="button" className="self-start text-xs text-mist underline hover:text-parchment" onClick={onRemove} aria-label={`Remove ${name} from the scene`}>
        Remove from the scene
      </button>
    </article>
  );
}
