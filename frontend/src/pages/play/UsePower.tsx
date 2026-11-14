import { useState } from "react";
import type { Cost, PlayView } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button } from "../../components/ui";
import { switchKey } from "./powers";
import type { makeTap } from "./tracker";

type TapWhat = Parameters<typeof makeTap>[0];

/** A discipline, power, technique or elder power with a plain cost, from the Pools tab's reference (issues #370 and #588). */
export type Costed = { name: string; cost?: Cost | null; switches?: string[] };

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
    { kind: "change", tracker: cost.tracker, amount: -cost.amount, note: switching ? "" : name },
    ...(switching ? [{ kind: "change" as const, tracker: switchKey(power.key), amount: 1 }] : []),
  ];
}

/** The switches a power can turn on that this character has: one Use button for each, or one for the spend alone. */
function choices(view: Pick<PlayView, "powers">, costed: Costed): (string | undefined)[] {
  const keys = (costed.switches ?? []).filter((k) => view.powers.some((p) => p.key === k));
  return keys.length > 0 ? keys : [undefined];
}

/** A switch's name without the power's: "flight form (bat)" for "Shape of the Beast: flight form (bat)". */
function shortName(name: string, power: string): string {
  return name.startsWith(`${power}: `) ? name.slice(power.length + 2) : name;
}

/**
 * "Use · 1 Blood" on a power with a plain cost: one tap spends it and turns on
 * the power's switch, with one Undo in the toast. A power with several switches
 * (Shape of the Beast's forms) has a button for each.
 */
export function UseButtons({ costed, view, use }: { costed: Costed; view: Pick<PlayView, "powers" | "blood" | "willpower" | "blood_name">; use: UseTaps }) {
  // A kept power on (#822): using it again replaces it, so it asks first.
  const [again, setAgain] = useState<string | null>(null);
  const cost = costed.cost;
  if (!cost) return null;
  const what = cost.tracker === "blood" ? view.blood_name : "Willpower";
  const left = cost.tracker === "blood" ? view.blood.value : view.willpower.value;
  const keys = choices(view, costed);
  return (
    <span className="flex flex-wrap justify-end gap-2">
      {keys.map((key) => {
        const name = key ? (view.powers.find((p) => p.key === key)?.name ?? costed.name) : costed.name;
        const shown = keys.length > 1 ? shortName(name, costed.name) : "Use";
        return (
          <Button
            key={key ?? ""}
            type="button"
            variant="danger"
            className="min-h-10 shrink-0 px-3 pointer-coarse:min-h-11"
            disabled={left < cost.amount}
            title={left < cost.amount ? `Not enough ${what}` : undefined}
            aria-label={`Use ${name}, ${cost.amount} ${what}`}
            onClick={() => {
              const power = key ? view.powers.find((p) => p.key === key) : undefined;
              if (power?.kept && power.on) setAgain(key ?? null);
              else use(usingTaps(view, cost, costed.name, key));
            }}
          >
            {shown} · {cost.amount} {what}
          </Button>
        );
      })}
      <Dialog title="Use it again?" open={again !== null} onClose={() => setAgain(null)}>
        <p className="text-sm">{view.powers.find((p) => p.key === again)?.name} is on, kept until you turn it off. Using it again replaces it: a character carries one at a time.</p>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => setAgain(null)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={() => {
              use(usingTaps(view, cost, costed.name, again ?? undefined));
              setAgain(null);
            }}
          >
            Use again · {cost.amount} {what}
          </Button>
        </div>
      </Dialog>
    </span>
  );
}
