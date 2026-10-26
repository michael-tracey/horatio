import { Link } from "react-router";
import type { RetainerOut, RetainerTrackOut } from "../../api/types";
import { useDates } from "../../dates";
import { backText, LOST_WORDS, retainerName, retainerSource } from "../character/retainers";
import { HEALTH_NOTE, NO_WILLPOWER, SPECIALTY_BONUS, bloodNote } from "./retainerPools";

type Tap = (change: { tracker: string; amount: number; label: string }) => void;

/**
 * Each Retainer as the NPC it is at a game (MET: VtM core p. 105): its test
 * pool, its specialties at the pool and 5 more, a ghoul's discipline and the
 * powers it reaches, and its health levels and Blood to tap. A Retainer staff
 * linked to an NPC opens that NPC's own sheet too.
 */
export function RetainerPools({ retainers, tracks, tap }: { retainers: RetainerOut[]; tracks: RetainerTrackOut[]; tap: Tap }) {
  if (retainers.length === 0) return null;
  return (
    <section aria-label="Retainers" className="grid gap-3 md:grid-cols-2">
      {retainers.map((r, i) => (
        <RetainerBlock key={r.tracker || i} retainer={r} track={tracks.find((t) => t.key === r.tracker)} tap={tap} />
      ))}
    </section>
  );
}

function RetainerBlock({ retainer: r, track, tap }: { retainer: RetainerOut; track?: RetainerTrackOut; tap: Tap }) {
  const name = retainerName(r);
  const source = retainerSource(r);
  const dates = useDates();
  // A lost Retainer is greyed out until its dots come back (p. 104).
  const back = backText(r, dates.date);
  return (
    <article aria-label={`Retainer: ${name}`} aria-disabled={r.away || undefined} className={`rounded-lg border border-ash bg-dusk p-3 ${r.away ? "opacity-50" : ""}`}>
      <header className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-base text-gold">
          {name}
          <span className="text-sm text-mist">
            {" "}
            · Retainer {r.dots}
            {r.ghoul ? " · ghoul" : ""}
            {source ? ` · ${source}` : ""}
          </span>
        </h2>
        <span className="text-right">
          <strong className="font-display text-2xl leading-none text-parchment" aria-label={`${name}'s pool: ${r.pool}`}>
            {r.pool}
          </strong>
          <span className="block text-xs text-mist">most actions</span>
        </span>
      </header>
      {r.lost && (
        <p className="mb-1 text-xs text-blood-bright" role="status">
          {LOST_WORDS[r.lost]}
          {r.lost_on ? ` ${dates.date(r.lost_on)}` : ""}. {back}
        </p>
      )}
      {r.npc_id && (
        <p className="mb-1 text-xs">
          Has its own sheet:{" "}
          <Link className="text-gold underline" to={`/play/characters/${r.npc_id}`}>
            {r.npc_name ?? "NPC"}
          </Link>
        </p>
      )}
      {r.specialties.length > 0 && (
        <ul className="mb-1 text-sm">
          {r.specialties.map((s) => (
            <li key={s} className="flex justify-between gap-3">
              <span>{s}</span>
              <strong className="text-parchment">{r.pool + SPECIALTY_BONUS}</strong>
            </li>
          ))}
        </ul>
      )}
      {r.discipline && (
        <div className="mb-1 text-sm">
          <p>
            {r.discipline} <span className="text-xs text-mist">to {r.dots}</span>
          </p>
          <ol className="pl-3 text-xs text-mist">
            {r.powers.map((p) => (
              <li key={`${p.level}/${p.name}`}>
                <span className="text-parchment">
                  {p.level}. {p.name}
                </span>{" "}
                {p.note}
              </li>
            ))}
          </ol>
        </div>
      )}
      {track && (
        <div className="mt-2 flex flex-col gap-2">
          <Track label={`${name}: health`} title="Health" tracker={`${track.key}/health`} value={track.health.value} most={track.health.most} tap={tap} off={r.away} />
          {track.health.value === 0 && <p className="text-xs text-blood-bright">{HEALTH_NOTE}</p>}
          {track.blood && <Track label={`${name}: Blood`} title="Blood" tracker={`${track.key}/blood`} value={track.blood.value} most={track.blood.most} tap={tap} off={r.away} />}
          {track.blood && <p className="text-xs text-mist">{bloodNote()}</p>}
        </div>
      )}
      <p className="mt-2 text-xs text-mist">{NO_WILLPOWER}</p>
    </article>
  );
}

function Track({ label, title, tracker, value, most, tap, off = false }: { label: string; title: string; tracker: string; value: number; most: number; tap: Tap; off?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm">
        {title}{" "}
        <span className="text-mist" aria-label={`${label}: ${value} of ${most}`}>
          {"●".repeat(value)}
          {"○".repeat(Math.max(0, most - value))}
        </span>
      </span>
      <span className="flex gap-1">
        <button
          type="button"
          aria-label={`Spend ${label}`}
          disabled={off || value <= 0}
          onClick={() => tap({ tracker, amount: -1, label })}
          className="grid h-9 min-w-9 place-items-center rounded-full border border-ash bg-night text-parchment hover:border-mist disabled:opacity-35"
        >
          −
        </button>
        <button
          type="button"
          aria-label={`Restore ${label}`}
          disabled={off || value >= most}
          onClick={() => tap({ tracker, amount: 1, label })}
          className="grid h-9 min-w-9 place-items-center rounded-full border border-ash bg-night text-parchment hover:border-mist disabled:opacity-35"
        >
          +
        </button>
      </span>
    </div>
  );
}
