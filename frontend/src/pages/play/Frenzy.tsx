import { useId, useState, type ReactNode } from "react";
import { FRENZY_TRIGGERS } from "./warnings";

/**
 * The frenzy rules a player needs at the table, in our own words with the
 * pages: what makes a frenzy test, resisting it, riding the wave, the three
 * frenzies, and coming out of one. Closed until asked for, behind a chevron.
 */
export function Frenzy() {
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <section className="rounded-lg border border-ash bg-dusk p-3">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panel}
          onClick={() => setOpen(!open)}
          className="-mx-1 flex min-h-10 w-full items-center gap-2 rounded px-1 text-left text-base text-gold hover:bg-ash/40"
        >
          <Chevron open={open} />
          Frenzy
          <span className="ml-auto text-xs text-mist">{open ? "Hide" : "The rules at the table"}</span>
        </button>
      </h2>
      {open && (
        <div id={panel} className="mt-2 flex flex-col gap-3 text-sm">
          <Part title="When you test" page="core, pp. 301–302">
            <p>With no Beast traits you never frenzy. With some, each of these makes you test to resist, and every count adds to the ones before:</p>
            <ul className="flex flex-col gap-1">
              {FRENZY_TRIGGERS.map((row) => (
                <li key={row.beast}>
                  <span className="text-gold">{row.beast}+:</span> {[...row.rage.map((t) => `${t} (rage)`), ...row.hunger.map((t) => `${t} (hunger)`), ...row.fear.map((t) => `${t} (fear)`)].join("; ")}.
                </li>
              ))}
            </ul>
          </Part>
          <Part title="Resisting" page="core, pp. 302–303">
            <p>Mental + Willpower against 10 + your Beast traits (+5 more at Humanity 2 or less). Or spend a Willpower to hold it off for the scene, or three turns in combat.</p>
          </Part>
          <Part title="Riding the wave" page="Vol. II Issue 1 update, pp. 94–95">
            <p>
              Instead of testing, you can react overtly and dramatically until the cause is gone. Rage: attack the source or an enemy, or make a show of force. Hunger: stalk the
              nearest mortal and feed. Fear: shriek or recoil, and keep your distance while watching it. It isn't frenzy, so powers that need a frenzy don't apply.
            </p>
          </Part>
          <Part title="In frenzy" page="core, pp. 301–302">
            <p>The Beast runs the show. You can still act and use your powers, but only towards what the frenzy wants, and it won't ignore its own safety: it'll put out flames on itself.</p>
            <ul className="flex flex-col gap-1">
              <li>
                <span className="text-gold">Rage:</span> attack what angered you until it's in torpor or unconscious. +1 to Physical attacks, −2 to Physical defence. Falling to
                Incapacitated turns it into fear.
              </li>
              <li>
                <span className="text-gold">Hunger:</span> attack the nearest mortal blood and drink until your Blood is full. +1 to Physical attacks, −2 to Physical defence.
              </li>
              <li>
                <span className="text-gold">Fear:</span> run from anything that could harm you or comes at you. Fight only when cornered, and flee at the first chance.
              </li>
            </ul>
            <p>Play it so it hurts what the character cares about most; work it out with your storyteller.</p>
          </Part>
          <Part title="Coming out" page="core, pp. 116, 301–302">
            <p>
              Rage ends when its target is down, or three turns after it escapes. Hunger ends when your Blood is full. Fear ends once you've escaped and hidden quietly for 10 minutes.
              Another vampire's Quell the Beast (Animalism) ends a frenzy at once, and a day's sleep clears every Beast trait.
            </p>
          </Part>
        </div>
      )}
    </section>
  );
}

function Part({ title, page, children }: { title: string; page: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="font-medium text-parchment">
        {title} <span className="text-xs font-normal text-mist">MET: VtM {page}</span>
      </h3>
      {children}
    </div>
  );
}

/** Points right when closed, down when open. */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-90" : ""}`}>
      <path d="M7.5 4.5 13 10l-5.5 5.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
