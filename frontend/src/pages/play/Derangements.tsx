import { useState } from "react";
import { Button, Input } from "../../components/ui";
import { TEMPORARY, tapId, type makeTap, type Shown } from "./tracker";
import { ShownWarning } from "./TrackerWarning";
import { derangementWarning } from "./warnings";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;
type RecordTap = (change: { tracker: string; amount: number; label: string }) => void;

const TITLE = "Derangement traits";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** Shown for a character with the Derangement flaw or a temporary derangement, and while any traits are marked. */
export function showsDerangements(view: Shown): boolean {
  const d = view.derangements;
  return d.flaws.length > 0 || d.temporary.some((t) => t.held) || d.value > d.least;
}

/**
 * Derangement traits (MET: VtM core, pp. 266-267): one marked each time the
 * character resists a derangement's trigger, up to 3, when the next trigger
 * brings a psychotic break. A severe response clears them all; a Malkavian
 * always keeps 1 (p. 57). Nothing clears them between games, so Reset for the
 * next game leaves them as they are. Taps are ordinary taps, logged with Undo.
 *
 * With them, the character's derangements: the Derangement flaws on the sheet,
 * and temporary ones the player adds and removes here (from Voice of Madness, a
 * clan weakness, a story's consequence), kept until they remove them.
 */
export function Derangements({ view, record, tap }: { view: Shown; record: RecordTap; tap: Tap }) {
  const [adding, setAdding] = useState(false);
  const sheet = adding && (
    <AddSheet
      onCancel={() => setAdding(false)}
      onAdd={(name, source) => {
        tap({ kind: "change", tracker: `${TEMPORARY}${tapId()}`, amount: 1, derangement: { name, source } });
        setAdding(false);
      }}
    />
  );
  if (!showsDerangements(view))
    return (
      <>
        <Button variant="secondary" className="min-h-11 w-full" onClick={() => setAdding(true)}>
          Add a temporary derangement…
        </Button>
        {sheet}
      </>
    );

  const { value, most, least, flaws, temporary } = view.derangements;
  const held = temporary.filter((t) => t.held);
  const down = () => record({ tracker: "derangements", amount: -1, label: TITLE });
  const up = () => record({ tracker: "derangements", amount: 1, label: TITLE });
  const severe = () => tap({ kind: "change", tracker: "derangements", amount: least - value, note: "Severe response" });
  const warning = derangementWarning(value, most, least);
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
            className={cx("h-9 w-9 rounded-md border transition-colors", i < value ? "border-gold/70 bg-gold/70" : "border-line bg-night", i < least && "opacity-60")}
          />
        ))}
      </div>
      {warning ? (
        <ShownWarning warning={warning} />
      ) : (
        <p className="mt-2 text-xs text-mist">Mark one for each trigger resisted.{least ? " Malkavians always have 1." : ""} Kept through Reset.</p>
      )}
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
      <ul className="mt-3 flex flex-col gap-1.5 border-t border-ash pt-2 text-sm" aria-label="Derangements">
        {flaws.map((flaw, i) => (
          <li key={`flaw-${i}`} className="flex min-h-9 items-center justify-between gap-2">
            <span>{flaw}</span>
            <span className="text-xs text-mist">On the sheet</span>
          </li>
        ))}
        {held.map((t) => (
          <li key={t.key} className="flex min-h-9 items-center justify-between gap-2">
            <span>
              <span className="block">{t.name}</span>
              <span className="block text-xs text-mist">Temporary{t.source ? `, from ${t.source}` : ""}</span>
            </span>
            <Button variant="ghost" className="min-h-9 px-2" aria-label={`Remove ${t.name}`} onClick={() => tap({ kind: "change", tracker: t.key, amount: -1 })}>
              Remove
            </Button>
          </li>
        ))}
      </ul>
      <Button variant="ghost" className="mt-1 min-h-10 px-0" onClick={() => setAdding(true)}>
        + Add a temporary derangement
      </Button>
      {sheet}
    </section>
  );
}

/** A temporary derangement's name and where it came from, as a sheet from the bottom of the screen. */
function AddSheet({ onAdd, onCancel }: { onAdd: (name: string, source: string) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gold/50 bg-dusk p-4 shadow-2xl" role="dialog" aria-label="Temporary derangement">
      <form
        className="mx-auto flex max-w-3xl flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) onAdd(name.trim(), source.trim());
        }}
      >
        <p className="text-sm text-mist">Kept from game to game, through Reset, until you remove it.</p>
        <label className="flex flex-col gap-1 text-sm">
          Derangement
          <Input autoFocus required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Phobia: fire" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Where it came from (optional)
          <Input maxLength={120} value={source} onChange={(e) => setSource(e.target.value)} placeholder="Voice of Madness" />
        </label>
        <div className="flex gap-2">
          <Button type="submit" className="min-h-12 flex-1" disabled={!name.trim()}>
            Add
          </Button>
          <Button type="button" variant="ghost" className="min-h-12" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
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
        "grid h-12 min-w-12 place-items-center rounded-full border px-3 text-lg font-semibold transition-colors active:scale-95 tap-off",
        strong ? "border-blood bg-blood text-parchment hover:bg-blood-bright" : "border-line bg-night text-parchment hover:border-mist",
      )}
    >
      {children}
    </button>
  );
}
