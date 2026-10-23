import { Button } from "../../components/ui";
import type { makeTap, Shown } from "./tracker";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;
type RecordTap = (change: { tracker: string; amount: number; label: string }) => void;

const TITLE = "Derangement traits";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** Shown for a character with a derangement on the sheet, and for any other while some are marked. */
export function showsDerangements(view: Shown): boolean {
  return view.derangements.held || view.derangements.value > view.derangements.least;
}

/**
 * Derangement traits (MET: VtM core, pp. 266-267): one marked each time the
 * character resists a derangement's trigger, up to 3, when the next trigger
 * brings a psychotic break. A severe response clears them all; a Malkavian
 * always keeps 1 (p. 57). Nothing clears them between games, so Reset for the
 * next game leaves them as they are. Taps are ordinary taps, logged with Undo.
 */
export function Derangements({ view, record, tap }: { view: Shown; record: RecordTap; tap: Tap }) {
  if (!showsDerangements(view)) return null;
  const { value, most, least } = view.derangements;
  const down = () => record({ tracker: "derangements", amount: -1, label: TITLE });
  const up = () => record({ tracker: "derangements", amount: 1, label: TITLE });
  const severe = () => tap({ kind: "change", tracker: "derangements", amount: least - value, note: "Severe response" });
  const hint =
    value >= most
      ? "Three: the next trigger brings a psychotic break."
      : `Mark one for each trigger resisted.${least ? " Malkavians always have 1." : ""} Kept through Reset.`;
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3" aria-label={TITLE}>
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-base text-gold">{TITLE}</h2>
        <span className="font-display text-2xl text-parchment" aria-label={`${TITLE}: ${value} of ${most}`}>
          {value}
          <span className="text-base text-mist"> / {most}</span>
        </span>
      </header>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={`${TITLE} boxes`}>
        {Array.from({ length: most }, (_, i) => (
          <button
            key={i}
            type="button"
            aria-label={i < value ? "Remove a Derangement trait" : "Mark a Derangement trait"}
            tabIndex={-1}
            disabled={i < least}
            onClick={i < value ? down : up}
            className={cx("h-9 w-9 rounded-md border transition-colors", i < value ? "border-gold/70 bg-gold/70" : "border-ash bg-night", i < least && "opacity-60")}
          />
        ))}
      </div>
      <p className={cx("mt-2 text-xs", value >= most ? "text-blood-bright" : "text-mist")}>{hint}</p>
      <div className="mt-3 flex items-center justify-between gap-2">
        <Button variant="secondary" className="min-h-12 rounded-full px-4" disabled={value <= least} onClick={severe}>
          Severe response
        </Button>
        <span className="flex gap-2">
          <RoundButton label="Remove a Derangement trait" onClick={down} disabled={value <= least}>
            −
          </RoundButton>
          <RoundButton label="Mark a Derangement trait" onClick={up} disabled={value >= most} strong>
            +
          </RoundButton>
        </span>
      </div>
    </section>
  );
}

function RoundButton({ label, onClick, disabled, strong, children }: { label: string; onClick: () => void; disabled: boolean; strong?: boolean; children: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "grid h-12 min-w-12 place-items-center rounded-full border px-3 text-lg font-semibold transition-colors active:scale-95 disabled:opacity-35",
        strong ? "border-blood bg-blood text-parchment hover:bg-blood-bright" : "border-ash bg-night text-parchment hover:border-mist",
      )}
    >
      {children}
    </button>
  );
}
