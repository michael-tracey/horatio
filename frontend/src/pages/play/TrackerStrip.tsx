import type { ReactNode } from "react";
import { TapButton } from "./PlayPage";
import { boxes } from "./powers";
import type { makeTap, Shown } from "./tracker";

type Tap = (what: Parameters<typeof makeTap>[0]) => unknown;

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * Blood, Willpower and health in a slim strip under the tabs, on every tab but
 * the Tracker (issue #370), so a power read on the Pools tab is paid for there.
 * "−" spends one, the same tap as the Tracker's, with its toast and Undo; a tap
 * on a name opens the Tracker.
 */
export function TrackerStrip({ view, tap, open }: { view: Shown; tap: Tap; open: () => void }) {
  const spend = (tracker: string) => tap({ kind: "change", tracker, amount: -1, damage: null });
  return (
    <div className="border-t border-ash/60" role="group" aria-label="Blood, Willpower and health">
      <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-1">
        <Count name={view.blood_name} value={view.blood.value} most={view.blood.most} open={open} spend={() => spend("blood")} />
        {view.willpower.most > 0 && <Count name="Willpower" short="WP" value={view.willpower.value} most={view.willpower.most} open={open} spend={() => spend("willpower")} />}
        <Health view={view} open={open} />
      </div>
    </div>
  );
}

/** A small name over a count, as a button that opens the Tracker. */
function Opens({ name, label, open, children }: { name: ReactNode; label: string; open: () => void; children: ReactNode }) {
  return (
    <button type="button" onClick={open} aria-label={label} className="flex min-h-10 flex-col justify-center text-left">
      <span className="text-[11px] leading-tight tracking-wide text-mist uppercase">{name}</span>
      {children}
    </button>
  );
}

function Count({ name, short, value, most, open, spend }: { name: string; short?: string; value: number; most: number; open: () => void; spend: () => void }) {
  return (
    <span className="flex items-center gap-2">
      <Opens
        name={
          short ? (
            <>
              <span className="sm:hidden">{short}</span>
              <span className="hidden sm:inline">{name}</span>
            </>
          ) : (
            name
          )
        }
        label={`${name} ${value} of ${most}: open the Tracker`}
        open={open}
      >
        <span className="font-display text-lg leading-tight text-parchment">
          {value}
          <span className="text-sm text-mist">/{most}</span>
        </span>
      </Opens>
      <TapButton label={`Spend ${name}`} onClick={spend} disabled={value <= 0} tone="blood" small>
        −
      </TapButton>
    </span>
  );
}

/** Health at a glance: a small box for each level, marked as on the Tracker. Damage is taken there, where its kind is chosen. */
function Health({ view, open }: { view: Shown; open: () => void }) {
  const marks = view.health.marks;
  const all = boxes(view);
  return (
    <Opens name="Health" label={`Health ${marks.length} of ${all.length} marked: open the Tracker`} open={open}>
      <span className="mt-1 flex max-w-28 flex-wrap gap-0.5" aria-hidden="true">
        {all.map((b, i) => (
          <span
            key={i}
            className={cx(
              "h-3 w-2.5 rounded-sm border",
              // A form's extra levels are edged in gold, as on the Tracker.
              marks[i] === "aggravated" ? "border-blood bg-blood" : marks[i] === "normal" ? "border-mist bg-mist" : b.from ? "border-gold/70 bg-night" : "border-line bg-night",
            )}
          />
        ))}
      </span>
    </Opens>
  );
}
