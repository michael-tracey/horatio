import type { PowerSwitch } from "../../api/types";
import { pageLabel } from "../../components/TraitInfo";
import { addedNote, formsOn, isPaused, pickKey, switchKey, withPicks } from "./powers";
import type { makeTap } from "./tracker";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;

/** Switch a form or power on or off: a tap, logged in the game with Undo like the rest. */
export const toggle = (tap: Tap, power: PowerSwitch) => tap({ kind: "change", tracker: switchKey(power.key), amount: power.on ? -1 : 1 });

const COUNTS = ["none", "one", "two", "three", "four"];

/** The character's own switches: not one used only on others, nor another's effect on it (#823), which have their own place. */
const ownSwitches = (powers: PowerSwitch[]) => powers.filter((p) => !p.foreign && p.target !== "other");

type PickChoice = PowerSwitch["options"][number];

/**
 * The options to pick from, with those whose amount is chosen each use (#824:
 * Tough's 1 to 3 Physical) together: one entry for the option, with a button for
 * each amount.
 */
function choicesOf(power: PowerSwitch): { name: string; label?: string | null; amounts: { option: PickChoice; amount: number | null }[] }[] {
  const found: { name: string; label?: string | null; amounts: { option: PickChoice; amount: number | null }[] }[] = [];
  for (const option of power.options) {
    const own = power.picks?.options?.find((o) => o.name === option.name);
    const base = own?.base;
    const last = found[found.length - 1];
    if (base && last?.name === base) last.amounts.push({ option, amount: own?.amount ?? null });
    else found.push({ name: base ?? option.name, label: base ? own?.amount_label : null, amounts: [{ option, amount: base ? (own?.amount ?? null) : null }] });
  }
  return found;
}

const pill = (picked: boolean) => `min-h-9 rounded-full border px-3 text-xs pointer-coarse:min-h-11 ${picked ? "border-gold/60 bg-gold/10 text-gold" : "border-line text-mist hover:text-parchment"}`;

/**
 * A power whose qualities are picked each use (issue #599), such as Flesh of
 * Marble's two Protective Gear qualities: while it is on, a button for each, and
 * what those picked do. Past its count, the oldest picked goes. An option whose
 * amount is chosen each use (#824) has a button for each amount, one picked at a time.
 */
function Picks({ power, tap }: { power: PowerSwitch; tap: Tap }) {
  const count = power.picks?.count ?? 0;
  const chosen = power.options.filter((o) => power.picked.includes(o.name));
  const pick = (o: PickChoice) => {
    const picked = power.picked.includes(o.name);
    tap({ kind: "change", tracker: pickKey(power.key, o.name), amount: picked ? -1 : 1 });
  };
  return (
    <div className="mt-1 pl-8" role="group" aria-label={`${power.name}: qualities`}>
      <p className="text-xs text-mist">
        Pick {COUNTS[count] ?? count} each use ({power.picked.length} picked).
      </p>
      <ul className="mt-1 flex flex-wrap gap-1">
        {choicesOf(power).map((c) =>
          c.amounts.length === 1 && c.amounts[0]!.amount === null ? (
            <li key={c.name}>
              <button type="button" aria-pressed={power.picked.includes(c.amounts[0]!.option.name)} title={c.amounts[0]!.option.play} onClick={() => pick(c.amounts[0]!.option)} className={pill(power.picked.includes(c.amounts[0]!.option.name))}>
                {c.name}
              </button>
            </li>
          ) : (
            <li key={c.name} className="flex items-center gap-1" role="group" aria-label={c.label ? `${c.name}: ${c.label}` : c.name}>
              <span className="text-xs text-mist">{c.label ? `${c.name} (${c.label})` : c.name}:</span>
              {c.amounts.map(({ option, amount }) => (
                <button key={option.name} type="button" aria-pressed={power.picked.includes(option.name)} aria-label={option.name} title={option.play} onClick={() => pick(option)} className={pill(power.picked.includes(option.name))}>
                  {amount}
                </button>
              ))}
            </li>
          ),
        )}
      </ul>
      {chosen.map((o) => (
        <p key={o.name} className="mt-1 text-xs text-parchment/80">
          {o.name}: {o.play}
          {pageLabel(o.page) && <span className="text-mist"> ({pageLabel(o.page)})</span>}
        </p>
      ))}
      {(power.option_picks ?? [])
        .filter((o) => power.picked.includes(o.name))
        .map((o) => (
          <OptionPicks key={o.key} option={o} tap={tap} />
        ))}
    </div>
  );
}

type OptionPicked = PowerSwitch["option_picks"][number];

/**
 * What is picked for one of a power's options while it is picked (#876): Bonecraft's
 * Body Weaponry, a weapon whose qualities are chosen by the weapon rules (core
 * p. 169), counted as an equipped item's. Past its count, the oldest goes.
 */
function OptionPicks({ option, tap }: { option: OptionPicked; tap: Tap }) {
  const chosen = option.options.filter((o) => option.picked.includes(o.name));
  return (
    <div className="mt-2 border-l border-ash/60 pl-3" role="group" aria-label={`${option.name}: qualities`}>
      <p className="text-xs text-mist">
        {option.name}: pick {COUNTS[option.count] ?? option.count} ({option.picked.length} picked).
      </p>
      <ul className="mt-1 flex flex-wrap gap-1">
        {option.options.map((q) => {
          const picked = option.picked.includes(q.name);
          return (
            <li key={q.name}>
              <button type="button" aria-pressed={picked} title={q.play} onClick={() => tap({ kind: "change", tracker: pickKey(option.key, q.name), amount: picked ? -1 : 1 })} className={pill(picked)}>
                {q.name}
              </button>
            </li>
          );
        })}
      </ul>
      {chosen.map((q) => (
        <p key={q.name} className="mt-1 text-xs text-parchment/80">
          {q.name}: {q.play}
          {pageLabel(q.page) && <span className="text-mist"> ({pageLabel(q.page)})</span>}
        </p>
      ))}
    </div>
  );
}

/**
 * What a kept power (issue #822) says beside it: kept through Reset until it is
 * turned off, and paused while a form is on for one that changes the normal form only.
 */
function KeptNote({ power, paused }: { power: PowerSwitch; paused: boolean }) {
  if (!power.kept) return null;
  return (
    <>
      <span className="block text-xs text-mist">{power.on ? "Kept through Reset until you turn it off." : "Lasts until undone: kept through Reset until you turn it off."}</span>
      {paused && <span className="block text-xs text-gold">Paused while you're in a form: it changes your normal form only.</span>}
    </>
  );
}

function Row({ power, tap, paused }: { power: PowerSwitch; tap: Tap; paused: boolean }) {
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
          <KeptNote power={power} paused={paused} />
          {power.notes.map((n) => (
            <span key={n} className="block text-xs text-mist">
              {n}
            </span>
          ))}
          {/* A view kept on the phone from before #601 has no `added`. */}
          {(power.added ?? []).map((a) => (
            <span key={addedNote(a)} className="block text-xs text-mist">
              {addedNote(a)}
            </span>
          ))}
          <span className="block text-xs text-mist">
            {power.origin} · {power.page}
          </span>
        </span>
      </label>
      {power.picks && power.on && <Picks power={power} tap={tap} />}
    </li>
  );
}

/**
 * "From your powers": the forms and powers on the sheet that hold only while
 * they are active, each with a switch. One form at a time (core p. 114): turning
 * one on turns the last off. With Ravenous Conglomeration (`forms` 2, Vol. 2
 * p. 249) two, and a third turns off the one on longest. The rest go with a form
 * and with each other.
 */
export function PowersList({ powers: all, forms: atOnce = 1, tap }: { powers: PowerSwitch[]; forms?: number; tap: Tap }) {
  const powers = ownSwitches(all);
  if (powers.length === 0) return null;
  const forms = powers.filter((p) => p.form);
  const others = powers.filter((p) => !p.form);
  return (
    <div>
      <h3 className="text-xs tracking-wide text-mist uppercase">From your powers</h3>
      {forms.length > 0 && (
        <>
          <p className="mt-1 text-xs text-mist">
            {atOnce > 1
              ? `Forms: ${atOnce === 2 ? "two" : atOnce} at once with Ravenous Conglomeration (Vol. 2 p. 249), never two of one power. Another turns off the one on longest.`
              : "Forms: one at a time (p. 114). Turning one on turns the last off."}
          </p>
          <ul className="divide-y divide-ash/60" aria-label="Forms">
            {forms.map((p) => (
              <Row key={p.key} power={p} tap={tap} paused={false} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <ul className="divide-y divide-ash/60 border-t border-ash/60" aria-label="Powers">
          {others.map((p) => (
            <Row key={p.key} power={p} tap={tap} paused={isPaused({ powers, forms: atOnce }, p)} />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Past this many powers on (not forms), the banner shows only their names and Off buttons, to stay short on a phone. */
const BRIEF_AFTER = 3;

/**
 * A short banner while a form or power is on: which, with its notes and what other
 * powers add to it, and a way back: Turn back for a form, Off for a power (#697).
 */
export function PowersBanner({ powers: all, forms: atOnce = 1, tap }: { powers: PowerSwitch[]; forms?: number; tap: Tap }) {
  // Another's effect on this one shows with the powers used on others, not here (#823).
  const powers = ownSwitches(all);
  const forms = formsOn({ powers });
  const others = powers.filter((p) => p.on && !p.form);
  if (forms.length === 0 && others.length === 0) return null;
  // With more than a few on, each is a name and its Off button: the notes are in the list.
  const brief = others.length > BRIEF_AFTER;
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
            {(f.added ?? []).map((a) => (
              <p key={addedNote(a)} className="text-xs text-mist">
                {addedNote(a)}
              </p>
            ))}
            <p className="text-xs text-mist">It ends if you sleep or fall into torpor (p. 114); switch it off then.</p>
          </div>
          <button type="button" className="shrink-0 text-xs text-mist underline hover:text-parchment" onClick={() => toggle(tap, f)}>
            Turn back
          </button>
        </div>
      ))}
      {others.length > 0 && (
        <ul className={forms.length ? "mt-1" : undefined} aria-label="Powers on">
          {others.map((p) => (
            <li key={p.key} className={`flex items-start justify-between gap-3 ${brief ? "" : "py-0.5"}`}>
              <div className="min-w-0">
                <p>
                  <span className="text-mist">{p.kept ? "Kept: " : "On: "}</span>
                  {withPicks(p)}
                  {isPaused({ powers, forms: atOnce }, p) && <span className="text-xs text-gold"> (paused while in a form)</span>}
                </p>
                {!brief && p.notes.length > 0 && <p className="text-xs text-mist">{p.notes.join(" ")}</p>}
                {!brief &&
                  (p.added ?? []).map((a) => (
                    <p key={addedNote(a)} className="text-xs text-mist">
                      {addedNote(a)}
                    </p>
                  ))}
              </div>
              <button
                type="button"
                className="min-h-9 shrink-0 text-xs text-mist underline hover:text-parchment pointer-coarse:min-h-11"
                onClick={() => toggle(tap, p)}
                aria-label={`Switch ${withPicks(p)} off`}
              >
                Off
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
