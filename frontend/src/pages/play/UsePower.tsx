import type { Cost, PlayView } from "../../api/types";
import { Button } from "../../components/ui";
import { switchKey } from "./powers";
import type { makeTap } from "./tracker";

type TapWhat = Parameters<typeof makeTap>[0];

/** A discipline or power with a plain cost, from the Pools tab's reference (issue #370). */
export type Costed = { name: string; cost?: Cost | null; switches?: string[] };

/** Spends taps made together, told in one toast whose Undo takes them all back. */
export type UseTaps = (whats: TapWhat[]) => unknown;

/**
 * The taps for using a power: its cost spent, then the switch it turns on, when
 * one is chosen and is off. A spend with no switch to say what it was for names
 * the power in its note: "Spent 1 Blood on Awe".
 */
export function usingTaps(view: Pick<PlayView, "powers">, cost: Cost, name: string, switchKeyOn?: string): TapWhat[] {
  const power = switchKeyOn ? view.powers.find((p) => p.key === switchKeyOn) : undefined;
  const switching = power && !power.on;
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
            onClick={() => use(usingTaps(view, cost, costed.name, key))}
          >
            {shown} · {cost.amount} {what}
          </Button>
        );
      })}
    </span>
  );
}
