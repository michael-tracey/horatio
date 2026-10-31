import { useState } from "react";
import type { PlayView } from "../../api/types";
import { Button, Select } from "../../components/ui";
import { drinkMost, drinkReminder, poolBoxes } from "./vitae";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/**
 * A ghoul's Blood on the Play View, in place of a vampire's (MET: VtM core p. 297):
 * its pool of 10, the vitae it can spend first, then the human Blood it cannot, then
 * what it has spent. Vitae is spent 1 a turn; "Drank vitae" adds up to 5, and the
 * reminder under it counts the month from the last drink.
 */
export function VitaeTracker({ view, spend, restore, drink }: { view: PlayView; spend: () => void; restore: () => void; drink: (amount: number) => void }) {
  const [asking, setAsking] = useState(false);
  const vitae = view.vitae!;
  const reminder = drinkReminder(vitae.last_drank_at, vitae.days);
  const value = view.blood.value;
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3" aria-label="Blood">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-base text-gold">Blood</h2>
        <span className="text-right font-display text-2xl text-parchment" aria-label={`Vitae: ${value} of ${view.blood.most}`}>
          {value}
          <span className="text-base text-mist"> / {view.blood.most} vitae</span>
        </span>
      </header>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Blood boxes">
        {poolBoxes(view).map((box, i) =>
          box === "vitae" ? (
            <button key={i} type="button" tabIndex={-1} aria-label="Spend Vitae" onClick={spend} className="h-10 w-10 rounded-md border border-blood bg-blood" />
          ) : (
            <span
              key={i}
              aria-label={box === "human" ? "Human Blood" : "Spent"}
              title={box === "human" ? "Human Blood: it can't be spent" : "Spent: it comes back as human Blood, 1 a day"}
              className={cx("h-10 w-10 rounded-md border", box === "human" ? "border-mist/60 bg-mist/30" : "border-line bg-night")}
            />
          ),
        )}
      </div>
      <p className="mt-2 text-xs text-mist">
        {vitae.human} human Blood, which can't be spent. Vitae goes 1 a turn, on healing, attributes or disciplines.
      </p>
      <p className={cx("mt-2 rounded-md px-3 py-2 text-sm", reminder.level === "ok" ? "text-mist" : "border border-blood/60 bg-blood/15")} role={reminder.level === "ok" ? undefined : "note"}>
        {reminder.text}
      </p>
      {asking && <DrinkSheet most={drinkMost(view)} onCancel={() => setAsking(false)} onSave={(n) => (drink(n), setAsking(false))} />}
      <div className="mt-3 flex items-center justify-end gap-2">
        <Button variant="secondary" className="min-h-12 rounded-full px-4" onClick={() => setAsking(true)}>
          Drank vitae
        </Button>
        <button
          type="button"
          aria-label="Spend Vitae"
          onClick={spend}
          disabled={value <= 0}
          className="grid h-12 min-w-12 place-items-center rounded-full border border-blood bg-blood px-3 text-lg font-semibold text-parchment transition-colors hover:bg-blood-bright active:scale-95 tap-off"
        >
          −
        </button>
        <button
          type="button"
          aria-label="Restore Vitae"
          title="A correction; a drink is Drank vitae"
          onClick={restore}
          disabled={value >= view.blood.most}
          className="grid h-12 min-w-12 place-items-center rounded-full border border-line bg-night px-3 text-lg font-semibold text-parchment transition-colors hover:border-mist active:scale-95 tap-off"
        >
          +
        </button>
      </div>
    </section>
  );
}

/** How much vitae was drunk: 1 to 5, never more than the pool holds. */
function DrinkSheet({ most, onSave, onCancel }: { most: number; onSave: (amount: number) => void; onCancel: () => void }) {
  const [amount, setAmount] = useState(most);
  return (
    <form
      className="mt-3 flex flex-wrap items-end gap-2 rounded-md border border-gold/50 p-3"
      aria-label="Drank vitae"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(amount);
      }}
    >
      <label className="flex flex-col gap-1 text-sm">
        Vitae drunk
        <Select value={amount} onChange={(e) => setAmount(Number(e.target.value))}>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </Select>
      </label>
      <p className="flex-1 text-xs text-mist">Never more than 5 vitae at once; drunk into a full pool, it takes the place of human Blood.</p>
      <Button type="submit" className="min-h-10">
        Save
      </Button>
      <Button type="button" variant="ghost" className="min-h-10" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}
