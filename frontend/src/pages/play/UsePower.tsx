import { useState } from "react";
import type { Cost, PlayView, PowerUse } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button } from "../../components/ui";
import { OnOtherPicker, type Picked } from "./OnOthers";
import { switchKey } from "./powers";
import type { makeTap } from "./tracker";
import { canPay, canSpend, costText, counterOf, ghouls, marked, offered, effectTaps, spendAmounts, unitsText, type UseView } from "./uses";

type TapWhat = Parameters<typeof makeTap>[0];

/** A discipline, power, technique or elder power with a plain cost, from the Pools tab's reference (issues #370 and #588). */
export type Costed = { name: string; cost?: Cost | null; switches?: string[]; uses?: PowerUse[] };

/** Whether the plain Use button shows: not where uses that spend take its place (issue #825). */
export function plainUse(costed: Costed): boolean {
  return !!costed.cost && !(costed.uses ?? []).some((u) => u.cost);
}

/** Spends taps made together, told in one toast whose Undo takes them all back. */
export type UseTaps = (whats: TapWhat[]) => unknown;

/**
 * The taps for using a power: its cost spent, then the switch it turns on, when
 * one is chosen and is off. A spend with no switch to say what it was for names
 * the power in its note: "Spent 1 Blood on Awe". The cost is spent on every use,
 * so a power paid for each time (Projectile's 1 Blood an attack) spends again
 * while its switch is on.
 */
export function usingTaps(view: Pick<PlayView, "powers">, cost: Cost, name: string, switchKeyOn?: string): TapWhat[] {
  const power = switchKeyOn ? view.powers.find((p) => p.key === switchKeyOn) : undefined;
  // A kept power used again replaces the one on (#822), so its switch is tapped again.
  const switching = power && (!power.on || power.kept);
  return [
    // Free while another switch waives it (#849): nothing is spent.
    ...(cost.amount > 0 ? [{ kind: "change" as const, tracker: cost.tracker, amount: -cost.amount, note: switching ? "" : name }] : []),
    ...(switching ? [{ kind: "change" as const, tracker: switchKey(power.key), amount: 1 }] : []),
  ];
}

/**
 * The switch on that makes using a power cost nothing, if any (#849: Quickened
 * Blood's five minutes of Celerity without Blood, core p. 230). One paused while a
 * form is on doesn't count.
 */
export function waivedBy(view: Pick<PlayView, "powers">, name: string): string | undefined {
  return view.powers.find((p) => p.on && !p.paused && p.waives.includes(name))?.name;
}

/** The switches a power can turn on that this character has: one Use button for each, or one for the spend alone. One used only on others has none here (#823). */
function choices(view: Pick<PlayView, "powers">, costed: Costed): (string | undefined)[] {
  const keys = (costed.switches ?? []).filter((k) => view.powers.some((p) => p.key === k && p.target !== "other" && !p.foreign));
  return keys.length > 0 ? keys : [undefined];
}

/** The switches of a power that can be used on another character (#823): Fleshcraft's reshaping. */
function forOthers(view: Pick<PlayView, "powers">, costed: Costed) {
  return (costed.switches ?? []).map((k) => view.powers.find((p) => p.key === k && !p.foreign)).filter((p) => p && p.target && p.target !== "self") as PlayView["powers"];
}

/**
 * The taps for using a power on another character (#823): its cost spent, naming the
 * power, and a note saying whom and what, which the server carries to them.
 */
export function onOtherTaps(cost: Cost | null | undefined, power: string, target: Picked, what: { switch?: string; use?: string; options?: string[] }): TapWhat[] {
  return [
    ...(cost && cost.amount > 0 ? [{ kind: "change" as const, tracker: cost.tracker, amount: -cost.amount, note: `${power} on ${target.name}` }] : []),
    {
      kind: "note" as const,
      note: `${power} on ${target.name}`,
      on_other: { character_id: target.id, character_name: target.name, power, switch: what.switch ?? null, use: what.use ?? null, options: what.options ?? [] },
    },
  ];
}

/** A switch's name without the power's: "flight form (bat)" for "Shape of the Beast: flight form (bat)". */
function shortName(name: string, power: string): string {
  return name.startsWith(`${power}: `) ? name.slice(power.length + 2) : name;
}

/** The amounts a cost can be spent at: its own, or each from it to its `most` (#824: Promises Like Steel's 1 to 3 Blood). */
export function amountsOf(cost: Cost): number[] {
  const most = cost.most ?? cost.amount;
  return Array.from({ length: Math.max(1, most - cost.amount + 1) }, (_, i) => cost.amount + i);
}

/**
 * "Use · 1 Blood" on a power with a plain cost: one tap spends it and turns on
 * the power's switch, with one Undo in the toast. A power with several switches
 * (Shape of the Beast's forms) has a button for each, and one whose player
 * chooses how much to spend (#824) a button for each amount.
 */
export function UseButtons({
  costed,
  view,
  use,
  online = true,
}: {
  costed: Costed;
  view: Pick<PlayView, "powers" | "blood" | "willpower" | "blood_name"> & Partial<Pick<PlayView, "character_id">>;
  use: UseTaps;
  online?: boolean;
}) {
  // A kept power on (#822): using it again replaces it, so it asks first.
  const [again, setAgain] = useState<{ key: string; amount: number } | null>(null);
  // Used on someone else (#823): the switch, while its picker is open.
  const [onOther, setOnOther] = useState<string | null>(null);
  const cost = costed.cost;
  if (!cost) return null;
  const what = cost.tracker === "blood" ? view.blood_name : "Willpower";
  const left = cost.tracker === "blood" ? view.blood.value : view.willpower.value;
  const keys = choices(view, costed);
  const others = view.character_id ? forOthers(view, costed) : [];
  const picking = others.find((p) => p.key === onOther);
  const free = waivedBy(view, costed.name);
  // Waived, it costs nothing: one button for each switch, spending none (#849).
  const amounts = free ? [0] : amountsOf(cost);
  const spending = (amount: number): Cost => ({ ...cost, amount });
  return (
    <span className="flex flex-wrap justify-end gap-2">
      {keys.flatMap((key) =>
        amounts.map((amount) => {
          const name = key ? (view.powers.find((p) => p.key === key)?.name ?? costed.name) : costed.name;
          const shown = keys.length > 1 ? shortName(name, costed.name) : "Use";
          const taps = usingTaps(view, spending(amount), costed.name, key);
          // Free and on already: there is nothing to do.
          const nothing = free !== undefined && taps.length === 0;
          return (
            <Button
              key={`${key ?? ""}/${amount}`}
              type="button"
              variant="danger"
              className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
              disabled={left < amount || nothing}
              title={left < amount ? `Not enough ${what}` : free ? `Free while ${free} is on` : undefined}
              aria-label={free ? `Use ${name}, free while ${free} is on` : `Use ${name}, ${amount} ${what}`}
              onClick={() => {
                const power = key ? view.powers.find((p) => p.key === key) : undefined;
                if (power?.kept && power.on && key) setAgain({ key, amount });
                else use(taps);
              }}
            >
              {shown} · {free ? (nothing ? "on, free" : "free") : `${amount} ${what}`}
            </Button>
          );
        }),
      )}
      {others.map((p) => (
        <Button
          key={`other-${p.key}`}
          type="button"
          variant="secondary"
          className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
          disabled={left < cost.amount}
          title={left < cost.amount ? `Not enough ${what}` : undefined}
          aria-label={`Use ${p.name} on someone else, ${cost.amount} ${what}`}
          onClick={() => setOnOther(p.key)}
        >
          {others.length > 1 ? shortName(p.name, costed.name) : "On someone else"} · {cost.amount} {what}
        </Button>
      ))}
      {picking && view.character_id && (
        <OnOtherPicker
          characterId={view.character_id}
          open
          title={`${picking.name}: on whom?`}
          options={(picking.picks?.options ?? []).map((o) => ({ name: o.name, play: o.note }))}
          count={picking.picks?.count ?? 0}
          confirm={`Use · ${cost.amount} ${what}`}
          online={online}
          onClose={() => setOnOther(null)}
          onPick={(target, options) => {
            use(onOtherTaps(cost, costed.name, target, { switch: picking.key, options }));
            setOnOther(null);
          }}
        />
      )}
      <Dialog title="Use it again?" open={again !== null} onClose={() => setAgain(null)}>
        <p className="text-sm">{view.powers.find((p) => p.key === again?.key)?.name} is on, kept until you turn it off. Using it again replaces it: a character carries one at a time.</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => setAgain(null)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={() => {
              if (again) use(usingTaps(view, spending(again.amount), costed.name, again.key));
              setAgain(null);
            }}
          >
            Use again · {again?.amount ?? cost.amount} {what}
          </Button>
        </div>
      </Dialog>
    </span>
  );
}

/**
 * The uses of a power that change the trackers besides spending (issue #825):
 * "Heal 1 normal · 1 Blood", "Won: +3 Blood", each its own button, made of
 * ordinary taps under one Undo. A use that would change nothing now is off, and
 * one whose switch is off isn't shown. "Once a turn" and the like are said, for
 * the player to keep to: the Play View counts no turns.
 */
export function UseEffects({ costed, view, use, online = true }: { costed: Costed; view: UseView; use: UseTaps; online?: boolean }) {
  const shown = (costed.uses ?? []).filter((u) => (u.target === "other" ? !!view.character_id && (!u.when || offered(view, u)) : offered(view, u)));
  if (shown.length === 0) return null;
  return (
    <ul className="mt-1 flex flex-col gap-1.5" aria-label={`Uses of ${costed.name}`}>
      {shown.map((u, i) => (
        <li key={`${u.label}-${u.target ?? "self"}-${i}`}>{u.target === "other" ? <UseOnOther power={costed.name} u={u} view={view} use={use} online={online} /> : <UseEffect power={costed.name} u={u} view={view} use={use} />}</li>
      ))}
    </ul>
  );
}

/**
 * A use on another character (#823): Corpore Sano healing someone else. Whom is
 * picked; what it heals there is worked out on their game, by the server.
 */
function UseOnOther({ power, u, view, use, online }: { power: string; u: PowerUse; view: UseView; use: UseTaps; online: boolean }) {
  const [picking, setPicking] = useState(false);
  const counter = counterOf(view, u);
  // What it spends of the user's own counter (#826: Rayzeel's Grace) is spent here.
  const charge = u.charges?.spend && counter ? u.charges.spend : 0;
  const suffix = [u.cost ? costText(view, u) : null, charge && counter ? unitsText(counter, charge) : null].filter(Boolean).map((t) => ` · ${t}`).join("");
  const paid = canPay(view, u) && canSpend(view, u);
  const said = [u.once ? `${u.once}.` : null, u.note].filter(Boolean).join(" ");
  const label = `${u.label} on someone else`;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="secondary"
        className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
        disabled={!paid}
        title={!canPay(view, u) ? `Not enough ${u.cost!.tracker === "blood" ? view.blood_name : "Willpower"}` : !paid && counter ? `Not enough ${counter.units}` : undefined}
        aria-label={`${power}: ${label}${suffix}`}
        onClick={() => setPicking(true)}
      >
        {label}
        {suffix}
      </Button>
      {(said || u.page) && (
        <span className="text-xs text-mist">
          {said}
          {u.page && <span className="whitespace-nowrap">{said ? " " : ""}({u.page})</span>}
        </span>
      )}
      {picking && view.character_id && (
        <OnOtherPicker
          characterId={view.character_id}
          open
          title={`${power}: ${u.label}, on whom?`}
          confirm={`${u.label}${suffix}`}
          online={online}
          onClose={() => setPicking(false)}
          onPick={(target) => {
            const spent = charge && counter ? [{ kind: "change" as const, tracker: counter.key, amount: -charge, note: `${power} on ${target.name}` }] : [];
            use([...spent, ...onOtherTaps(u.cost, power, target, { use: u.label })]);
            setPicking(false);
          }}
        />
      )}
    </div>
  );
}

function UseEffect({ power, u, view, use }: { power: string; u: PowerUse; view: UseView; use: UseTaps }) {
  const [asking, setAsking] = useState(false);
  const counter = counterOf(view, u);
  const spends = spendAmounts(view, u);
  // A spend of a counter (#826) shows with the cost: "Throw them · 1 charge".
  const charged = (n?: number) => (n && counter ? ` · ${unitsText(counter, n)}` : "");
  const suffix = (u.cost ? ` · ${costText(view, u)}` : "") + charged(spends.length === 1 ? spends[0] : undefined);
  const said = [u.once ? `${u.once}.` : null, u.note].filter(Boolean).join(" ");
  const short = !canPay(view, u) ? `Not enough ${u.cost!.tracker === "blood" ? view.blood_name : "Willpower"}` : !canSpend(view, u) && counter ? `Not enough ${counter.units}` : "Nothing to change now";
  const button = (label: string, taps: ReturnType<typeof effectTaps>, key?: string, end: string = suffix) => (
    <Button
      key={key ?? label}
      type="button"
      variant="secondary"
      className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
      disabled={taps.length === 0}
      title={taps.length === 0 ? short : undefined}
      aria-label={`${power}: ${label}${end}`}
      onClick={() => use(taps)}
    >
      {label}
      {end}
    </Button>
  );
  let body;
  if (u.retainer) {
    const kept = ghouls(view, u);
    body =
      kept.length === 0 ? (
        <span className="text-xs text-mist">{u.animal ? "No animal ghoul Retainer with health left to take it." : "No ghoul Retainer with health left to take it."}</span>
      ) : (
        kept.map((r) => button(`${u.label} to ${r.name || "Retainer"}`, effectTaps(view, u, power, { retainer: r.key }), r.key))
      );
  } else if (u.heal?.damage === "asked") {
    body = asking ? (
      <Asked power={power} u={u} view={view} suffix={suffix} done={() => setAsking(false)} use={use} />
    ) : (
      <Button
        type="button"
        variant="secondary"
        className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
        disabled={!canPay(view, u) || view.health.marks.length === 0}
        title={!canPay(view, u) ? short : view.health.marks.length === 0 ? "No damage to undo" : undefined}
        aria-label={`${power}: ${u.label}${suffix}`}
        onClick={() => setAsking(true)}
      >
        {u.label}
        {suffix}
      </Button>
    );
  } else if (spends.length > 1) {
    // The player says how many to spend (#826: Vengeful Strike's charge a point).
    const cost = u.cost ? ` · ${costText(view, u)}` : "";
    body = spends.map((n) => button(u.label, effectTaps(view, u, power, { spend: n }), `${u.label}/${n}`, cost + charged(n)));
  } else {
    body = button(u.label, effectTaps(view, u, power));
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {body}
      {(said || u.page) && (
        <span className="text-xs text-mist">
          {said}
          {u.page && <span className="whitespace-nowrap">{said ? " " : ""}({u.page})</span>}
        </span>
      )}
    </div>
  );
}

/** How much damage to undo (Indestructible's "this turn"), which only the player knows. */
function Asked({ power, u, view, suffix, done, use }: { power: string; u: PowerUse; view: UseView; suffix: string; done: () => void; use: UseTaps }) {
  const most = marked(view);
  const [normal, setNormal] = useState(0);
  const [aggravated, setAggravated] = useState(0);
  const taps = effectTaps(view, u, power, { asked: { normal, aggravated } });
  const step = (label: string, value: number, top: number, set: (n: number) => void) => (
    <span className="flex items-center gap-1 text-sm">
      <Button type="button" variant="ghost" className="min-h-9 px-2" aria-label={`Less ${label}`} disabled={value <= 0} onClick={() => set(value - 1)}>
        −
      </Button>
      <span aria-live="polite">
        {value} {label}
      </span>
      <Button type="button" variant="ghost" className="min-h-9 px-2" aria-label={`More ${label}`} disabled={value >= top} onClick={() => set(value + 1)}>
        +
      </Button>
    </span>
  );
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-ash p-2" role="group" aria-label={`${power}: how much damage`}>
      {step("normal", normal, most.normal, setNormal)}
      {step("aggravated", aggravated, most.aggravated, setAggravated)}
      <Button
        type="button"
        variant="secondary"
        className="min-h-10 px-3"
        disabled={normal + aggravated === 0 || taps.length === 0}
        onClick={() => {
          use(taps);
          done();
        }}
      >
        Heal {normal + aggravated}{suffix}
      </Button>
      <Button type="button" variant="ghost" className="min-h-10 px-3" onClick={done}>
        Cancel
      </Button>
    </div>
  );
}
