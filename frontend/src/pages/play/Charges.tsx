import type { Charge, PlayView } from "../../api/types";
import { Button } from "../../components/ui";
import { switchKey } from "./powers";
import type { makeTap } from "./tracker";
import type { UseTaps } from "./UsePower";

type TapWhat = Parameters<typeof makeTap>[0];

/**
 * The taps for letting a counter's charges go (#826): down to what it keeps
 * (Kineticism's 1 going into a fight, Vol. 2 p. 72), and the switch it names off
 * (Reaper's Due's mark). None when nothing would change.
 */
export function fadeTaps(view: Pick<PlayView, "powers">, charge: Pick<Charge, "key" | "value">, fade: Charge["fades"][number]): TapWhat[] {
  const off = fade.off ? view.powers.find((p) => p.key === fade.off && p.on) : undefined;
  return [
    ...(charge.value > fade.keep ? [{ kind: "change" as const, tracker: charge.key, amount: fade.keep - charge.value }] : []),
    ...(off ? [{ kind: "change" as const, tracker: switchKey(off.key), amount: -1 }] : []),
  ];
}

/** The counters to show in one place: with a discipline, under one of its powers, or with another power. */
export function chargesFor(view: Partial<Pick<PlayView, "charges">>, where: { discipline?: string; power?: string; other?: string }): Charge[] {
  return (view.charges ?? []).filter((c) =>
    where.other !== undefined ? c.other === where.other : c.discipline === where.discipline && (c.power ?? undefined) === where.power,
  );
}

/**
 * A power's charges, points or stack at this game (#826): "Kineticism charges 2 / 5",
 * what they are, and a button for each way they fade. The Play View counts no
 * fights or minutes, so the player says when.
 */
export function Charges({ charges, view, use }: { charges: Charge[]; view: Pick<PlayView, "powers">; use: UseTaps }) {
  if (charges.length === 0) return null;
  return (
    <ul className="mb-2 flex flex-col gap-1.5">
      {charges.map((c) => (
        <li key={c.key} className="rounded-md border border-ash/70 px-2 py-1.5" aria-label={c.name}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm">
              <span className="font-semibold">{c.name}</span>{" "}
              <span className="font-display text-lg text-gold" aria-live="polite">
                {c.value}
              </span>
              <span className="text-mist"> / {c.most}</span>
            </p>
            <span className="flex flex-wrap gap-2">
              {c.fades.map((f) => {
                const taps = fadeTaps(view, c, f);
                return (
                  <Button
                    key={f.label}
                    type="button"
                    variant="ghost"
                    className="min-h-10 px-3 pointer-coarse:min-h-11"
                    disabled={taps.length === 0}
                    title={taps.length === 0 ? "Nothing to let go" : undefined}
                    aria-label={`${c.name}: ${f.label}`}
                    onClick={() => use(taps)}
                  >
                    {f.label}
                    {f.keep > 0 ? ` · keep ${f.keep}` : ""}
                  </Button>
                );
              })}
            </span>
          </div>
          {(c.note || c.page) && (
            <p className="text-xs text-mist">
              {c.note}
              {c.page && <span className="whitespace-nowrap">{c.note ? " " : ""}({c.page})</span>}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
