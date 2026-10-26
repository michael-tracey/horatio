import type { PowerSwitch } from "../../api/types";
import { formsOn, switchKey } from "./powers";
import type { makeTap } from "./tracker";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;

/** Switch a form or power on or off: a tap, logged in the game with Undo like the rest. */
export const toggle = (tap: Tap, power: PowerSwitch) => tap({ kind: "change", tracker: switchKey(power.key), amount: power.on ? -1 : 1 });

function Row({ power, tap }: { power: PowerSwitch; tap: Tap }) {
  return (
    <li className="py-2">
      <label className="flex min-h-10 items-start gap-3">
        <input
          type="checkbox"
          className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--color-gold)]"
          checked={power.on}
          onChange={() => toggle(tap, power)}
          aria-label={`${power.name} on`}
        />
        <span className="min-w-0">
          <span className={power.on ? "text-parchment" : "text-mist"}>{power.name}</span>
          {power.changes.length > 0 && <span className="block text-xs text-parchment/80">{power.changes.join(" · ")}</span>}
          {power.notes.map((n) => (
            <span key={n} className="block text-xs text-mist">
              {n}
            </span>
          ))}
          <span className="block text-xs text-mist">
            {power.origin} · {power.page}
          </span>
        </span>
      </label>
    </li>
  );
}

/**
 * "From your powers": the forms and powers on the sheet that hold only while
 * they are active, each with a switch. One form at a time (core p. 114): turning
 * one on turns the last off. The rest go with a form and with each other.
 */
export function PowersList({ powers, tap }: { powers: PowerSwitch[]; tap: Tap }) {
  if (powers.length === 0) return null;
  const forms = powers.filter((p) => p.form);
  const others = powers.filter((p) => !p.form);
  return (
    <div>
      <h3 className="text-xs tracking-wide text-mist uppercase">From your powers</h3>
      {forms.length > 0 && (
        <>
          <p className="mt-1 text-xs text-mist">Forms: one at a time (p. 114). Turning one on turns the last off.</p>
          <ul className="divide-y divide-ash/60" aria-label="Forms">
            {forms.map((p) => (
              <Row key={p.key} power={p} tap={tap} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <ul className="divide-y divide-ash/60 border-t border-ash/60" aria-label="Powers">
          {others.map((p) => (
            <Row key={p.key} power={p} tap={tap} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** A short banner while a form or power is on: which, with its notes, and a way back. */
export function PowersBanner({ powers, tap }: { powers: PowerSwitch[]; tap: Tap }) {
  const forms = formsOn({ powers });
  const others = powers.filter((p) => p.on && !p.form);
  if (forms.length === 0 && others.length === 0) return null;
  return (
    <section className="rounded-lg border border-gold/60 bg-gold/10 px-3 py-2 text-sm" aria-label="Switched on now">
      {forms.map((f) => (
        <div key={f.key} className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p>
              <span className="text-mist">In </span>
              <strong className="font-semibold text-gold">{f.name}</strong>
            </p>
            {f.notes.length > 0 && <p className="text-xs text-mist">{f.notes.join(" ")}</p>}
            <p className="text-xs text-mist">It ends if you sleep or fall into torpor (p. 114); switch it off then.</p>
          </div>
          <button type="button" className="shrink-0 text-xs text-mist underline hover:text-parchment" onClick={() => toggle(tap, f)}>
            Turn back
          </button>
        </div>
      ))}
      {others.length > 0 && (
        <p className={forms.length ? "mt-1" : undefined}>
          <span className="text-mist">On: </span>
          {others.map((p) => p.name).join(", ")}
        </p>
      )}
    </section>
  );
}
