import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CarriedOut, ConditionOut, PlayStatusOut, PlayView, StatusChoiceIn, StatusIn } from "../../api/types";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Button, ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { capText, endingText, outsiderText, suppressedText } from "../character/status";
import { AddStatus, useStatus } from "../character/StatusCard";
import { Others } from "./Others";
import type { Shown } from "./tracker";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

function Panel({ title, aside, children }: { title: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-base text-gold">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** One choice for the game; what is left out stays as it is. */
type Choice = Partial<StatusChoiceIn>;

const GROUPS = [
  { type: "Negative", title: "Negative status" },
  { type: "Abiding", title: "Abiding status" },
  { type: "Innate", title: "Innate status" },
  { type: "Fleeting", title: "Fleeting status" },
] as const;

/** "Noble; Authority (while the Prince is absent)". */
function gives(status: { name: string; condition: string }[]): string {
  return status.map((s) => (s.condition ? `${s.name} (${s.condition})` : s.name)).join(", ");
}

/**
 * The Play View's Status tab (MET: VTM pp. 310-317): the status the character carries
 * into this game, each with what it does held and spent, and a tap to spend it, with
 * Undo; the choices for the game (one source of abiding status, a title's status for
 * the night, a ruler away); its titles in the game's troupe; and adding status at the
 * game, where the troupe lets players keep their own; and the others at the game,
 * whose status a member of the same sect knows.
 */
export function StatusTab({
  view,
  spend,
  undo,
  online,
  onChange,
}: {
  view: Shown;
  spend: (item: CarriedOut) => void;
  undo: (tapId: string) => void;
  online: boolean;
  onChange: (view: PlayView) => Promise<void>;
}) {
  const status = view.status;
  // Who may add status, and whether the viewer is staff: the troupe's setting, as the sheet has it.
  const standing = useStatus(view.character_id);
  const [adding, setAdding] = useState(false);
  const path = { params: { path: { character_id: view.character_id } } };
  const choose = useAction(async (choice: Choice) =>
    onChange(await unwrap(api.PUT("/api/characters/{character_id}/play/status/choice", { ...path, body: { chosen: {}, absent: {}, ...choice } }))),
  );
  if (!status) return <p className="py-8 text-center text-mist">This character has no sect status.</p>;
  const staff = standing.data?.staff ?? false;
  const fleeting = status.carried.filter((c) => c.type === "Fleeting" && !c.suppressed && !(c.spent && c.key.startsWith("held:")));
  const character = { id: view.character_id, name: view.character_name, kind: view.kind };
  const add = async (body: StatusIn) => onChange(await unwrap(api.POST("/api/characters/{character_id}/play/status", { ...path, body })));
  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Status"
        aside={
          standing.data?.acting &&
          !adding && (
            <Button variant="secondary" disabled={!online} onClick={() => setAdding(true)}>
              Add status
            </Button>
          )
        }
      >
        <p className="text-sm">
          {status.accepted ? `${status.accepted} by the ${status.sect}` : outsiderText(status)}
          {status.troupe_name && <span className="text-mist"> · at {status.troupe_name}</span>}
        </p>
        <p className="mt-1 text-xs text-mist">
          Fleeting: {fleeting.length} of {status.fleeting_cap}
          {capText(status.cap_why) && ` (${capText(status.cap_why)})`}. Spending is yours, whatever the troupe’s setting; abiding and innate status comes back at the next game.
        </p>
        <Suppressed status={status} />
        {adding && standing.data && (
          <AddStatus character={character} status={standing.data} submit={add} atGame onDone={() => setAdding(false)} />
        )}
      </Panel>
      <ThisGame status={status} staff={staff} online={online} pending={choose.isPending} choose={(body) => choose.mutate(body)} />
      <ErrorText error={choose.error} />
      {GROUPS.map((g) => {
        const items = status.carried.filter((c) => c.type === g.type);
        if (items.length === 0) return null;
        return (
          <Panel key={g.type} title={g.title}>
            <ul className="divide-y divide-ash">
              {items.map((item) => (
                <StatusRow key={item.key} item={item} spend={() => spend(item)} undo={item.spent_by ? () => undo(item.spent_by!) : undefined} />
              ))}
            </ul>
          </Panel>
        );
      })}
      {status.carried.length === 0 && !status.choosing && <p className="text-sm text-mist">No status to carry into this game.</p>}
      <Titles status={status} />
      <Others view={view} undo={undo} online={online} />
    </div>
  );
}

function Suppressed({ status }: { status: PlayStatusOut }) {
  const dates = useDates();
  if (status.suppressed.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-col gap-1">
      {status.suppressed.map((s) => (
        <li key={s.id ?? s.kind} className="rounded-md border border-blood/60 bg-blood/15 px-3 py-2 text-sm">
          {suppressedText(s, dates.day)}
        </li>
      ))}
    </ul>
  );
}

/**
 * As the game begins: the one source of abiding status (MET: VTM p. 311), and its
 * title's status for the night. Each is the holder's to choose once; staff change it.
 */
function ThisGame({
  status,
  staff,
  online,
  pending,
  choose,
}: {
  status: PlayStatusOut;
  staff: boolean;
  online: boolean;
  pending: boolean;
  choose: (body: Choice) => void;
}) {
  const [changing, setChanging] = useState(false);
  if (status.sources.length < 2 && status.conditions.length === 0) return null;
  const picking = status.choosing || changing;
  const disabled = !online || pending;
  return (
    <Panel title="This game">
      {status.sources.length > 1 &&
        (picking ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm">Choose your one source of abiding status for this game (MET: VTM p. 311). Innate status always applies.</p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {status.sources.map((s) => (
                <li key={s.name}>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-label={`Choose ${s.name}`}
                    onClick={() => {
                      choose({ source: s.name });
                      setChanging(false);
                    }}
                    className={cx(
                      "flex min-h-12 w-full flex-col items-start rounded-md border px-3 py-2 text-left disabled:opacity-50",
                      s.name === status.source ? "border-gold bg-gold/10" : "border-ash bg-night hover:border-mist",
                    )}
                  >
                    <span className="text-parchment">{s.name}</span>
                    <span className="text-xs text-mist">{gives(s.status)}</span>
                  </button>
                </li>
              ))}
            </ul>
            {!online && <p className="text-xs text-mist">Choosing needs a connection.</p>}
            {changing && (
              <Button variant="ghost" className="self-start" onClick={() => setChanging(false)}>
                Cancel
              </Button>
            )}
          </div>
        ) : (
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span>
              Abiding status from <span className="text-gold">{status.source ?? "no source"}</span>
              {status.source_chosen && <span className="text-mist">, chosen for this game</span>}
              {status.source_chosen && !status.source && <span className="text-mist">: the title is gone</span>}.
            </span>
            {staff && (
              <Button variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setChanging(true)}>
                Change
              </Button>
            )}
          </p>
        ))}
      {status.conditions.length > 0 && (
        <ul className="mt-2 flex flex-col gap-2">
          {status.conditions.map((c) => (
            <ConditionRow key={`${c.kind}/${c.absent_title ?? c.title}`} condition={c} staff={staff} disabled={disabled} choose={choose} />
          ))}
        </ul>
      )}
      {(status.source_chosen || status.conditions.some((c) => c.chosen || c.away)) && (
        <p className="mt-2 text-xs text-mist">Your choices are locked for this game; staff can change them.</p>
      )}
    </Panel>
  );
}

function ConditionRow({ condition: c, staff, disabled, choose }: { condition: ConditionOut; staff: boolean; disabled: boolean; choose: (body: Choice) => void }) {
  if (c.kind === "choose") {
    return (
      <li className="flex flex-col gap-1.5 text-sm">
        <span>
          As {c.title}, tonight: {c.chosen ? <span className="text-gold">{c.chosen}</span> : <span className="text-mist">choose one</span>}
        </span>
        {(!c.chosen || staff) && (
          <span className="flex flex-wrap gap-2">
            {c.options.map((o) => (
              <Button key={o} variant={o === c.chosen ? "primary" : "secondary"} disabled={disabled || o === c.chosen} onClick={() => choose({ chosen: { [c.title]: o } })}>
                {o}
              </Button>
            ))}
          </span>
        )}
      </li>
    );
  }
  const absent = c.absent_title ?? "";
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 text-sm">
      <span>
        {c.away ? (
          <>
            The {absent} is absent: <span className="text-gold">{c.options.join(", ")}</span>
          </>
        ) : (
          <>
            While the {absent} is absent, {c.title} gives {c.options.join(", ")}.
          </>
        )}
      </span>
      {!c.away ? (
        <Button variant="secondary" disabled={disabled} onClick={() => choose({ absent: { [absent]: true } })}>
          The {absent} is absent
        </Button>
      ) : (
        staff && (
          <Button variant="ghost" disabled={disabled} onClick={() => choose({ absent: { [absent]: false } })}>
            The {absent} is here
          </Button>
        )
      )}
    </li>
  );
}

function StatusRow({ item, spend, undo }: { item: CarriedOut; spend: () => void; undo?: () => void }) {
  const dates = useDates();
  const about = item.about;
  const page = pageLabel(about?.page);
  const forGood = item.key.startsWith("held:");
  return (
    <li className="flex items-start gap-3 py-2">
      <div className={cx("min-w-0 flex-1 text-sm", (item.spent || item.suppressed) && "opacity-60")}>
        <p>
          <span className={cx("text-parchment", item.spent && "line-through")}>{item.name}</span>
          <span className="text-xs text-mist"> · {item.type === "Fleeting" || item.type === "Negative" ? `from ${item.source}` : item.source}</span>
          {item.suppressed && (
            <span className="ml-2">
              <Badge tone="blood">suppressed</Badge>
            </span>
          )}
        </p>
        {about?.passive && <p className="text-xs text-mist">Held: {about.passive}</p>}
        {about?.spent && <p className="text-xs text-mist">Spent: {about.spent}</p>}
        {about?.censure && <p className="text-xs text-mist">Censure: {about.censure}</p>}
        {about?.punishment && <p className="text-xs text-mist">Punishment: {about.punishment}</p>}
        {item.ending && <p className="text-xs text-gold">{endingText(item.ending, dates.day)}.</p>}
        {item.story && <p className="text-xs text-mist">{item.story}</p>}
        {page && <p className="text-xs text-mist">{page}</p>}
      </div>
      {item.spendable &&
        (item.spent ? (
          <span className="flex flex-col items-end gap-1">
            <span className="text-xs text-mist">{forGood ? "Spent for good" : "Spent"}</span>
            {undo && (
              <Button variant="secondary" className="min-h-10" aria-label={`Undo spending ${item.name}`} onClick={undo}>
                Undo
              </Button>
            )}
          </span>
        ) : (
          <Button className="min-h-12 min-w-20" aria-label={`Spend ${item.name}`} onClick={spend}>
            Spend
          </Button>
        ))}
    </li>
  );
}

function Titles({ status }: { status: PlayStatusOut }) {
  if (status.titles.length === 0) return null;
  return (
    <Panel title={status.troupe_name ? `Titles in ${status.troupe_name}` : "Titles"}>
      <ul className="flex flex-col gap-1 text-sm">
        {status.titles.map((t) => (
          <li key={t.name}>
            <span className={t.active ? "text-gold" : "text-parchment"}>{t.name}</span>
            {!t.active ? (
              <span className="text-mist">: not active, so no status</span>
            ) : t.status.length > 0 ? (
              `: ${gives(t.status)}`
            ) : (
              <span className="text-mist">: no status</span>
            )}
            {t.next_game && <span className="text-xs text-mist"> (given during this game: its status from the next)</span>}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
