import type { SummonOut } from "../../api/types";
import { Track } from "./RetainerPools";

type Tap = (change: { tracker: string; amount: number; label: string }) => void;

/**
 * The allies the character's powers have called up at this game (issue #827): Arms
 * of the Abyss, zombies, a bound wraith. Each has its own health levels to tap, as a
 * Retainer's are, and a Dismiss; all are gone when the game ends. They are called up
 * by the power's use on the Pools tab, which pays for them.
 */
export function Allies({ summons, tap }: { summons: SummonOut[]; tap: Tap }) {
  if (summons.length === 0) return null;
  return (
    <section aria-label="Allies" className="grid gap-3 md:grid-cols-2">
      {summons.map((s) => (
        <SummonBlock key={s.key} summon={s} tap={tap} />
      ))}
    </section>
  );
}

function SummonBlock({ summon: s, tap }: { summon: SummonOut; tap: Tap }) {
  const out = s.allies.filter((a) => a.out).sort((a, b) => a.order - b.order);
  return (
    <article aria-label={`Allies: ${s.name}`} className="rounded-lg border border-ash bg-dusk p-3">
      <header className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="text-base text-gold">
          {s.name}
          <span className="text-sm text-mist"> · {s.origin}</span>
        </h2>
        <span className="text-sm text-mist" aria-label={`${s.name}: ${out.length} of ${s.most} out`}>
          {out.length} of {s.most} out
        </span>
      </header>
      {s.note && (
        <p className="mb-2 text-xs text-mist">
          {s.note} <span className="whitespace-nowrap">({s.page})</span>
        </p>
      )}
      {out.length === 0 ? (
        <p className="text-xs text-mist">None out. Call them up with the power on the Pools tab.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {out.map((a) => (
            <li key={a.key} aria-label={a.name} className="flex flex-col gap-1 border-t border-ash pt-2 first:border-0 first:pt-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-parchment">{a.name}</span>
                <button
                  type="button"
                  aria-label={`Dismiss ${a.name}`}
                  onClick={() => tap({ tracker: a.key, amount: -1, label: a.name })}
                  className="min-h-9 rounded-full border border-line bg-night px-3 text-sm text-parchment hover:border-mist tap-off"
                >
                  Dismiss
                </button>
              </div>
              {a.health && <Track label={`${a.name}: health`} title="Health" tracker={`${a.key}/health`} value={a.health.value} most={a.health.most} tap={tap} />}
              {a.health?.value === 0 && <p className="text-xs text-blood-bright">Out of health levels: destroyed, or out of the fight.</p>}
              {a.blood && <Track label={`${a.name}: Blood`} title="Blood" tracker={`${a.key}/blood`} value={a.blood.value} most={a.blood.most} tap={tap} />}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
