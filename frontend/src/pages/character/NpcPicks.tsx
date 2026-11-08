import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, NpcPicksOut as PicksOut, NpcPoolOut as PoolOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Badge, Button, Card, ErrorText, Select } from "../../components/ui";
import { useAction } from "../../hooks";

type Placed = PoolOut["placed"][number];
type Body = { category: string; name: string; detail: string; rating?: number; replacing?: { name: string; detail: string } };

const key = (name: string, detail: string) => (detail ? `${name}\u0000${detail}` : name);
const shown = (name: string, detail: string) => (detail ? `${name}: ${detail}` : name);

/**
 * An NPC built without the wizard has its creation picks fitted to its sheet, so its
 * creation dots are free as a player character's are (#527). Staff put the fitting
 * right where the player picked otherwise: a pick placed by hand stays, one taken off
 * a trait stays off, and the rest are fitted around them.
 */
export function NpcPicks({ character }: { character: CharacterOut }) {
  const path = { params: { path: { character_id: character.id } } };
  const picks = useQuery({ queryKey: ["npc-picks", character.id], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/npc/picks", path)) });
  const place = useAction((body: Body) => unwrap(api.PUT("/api/characters/{character_id}/npc/picks", { ...path, body })));
  const off = useAction((body: Body) => unwrap(api.POST("/api/characters/{character_id}/npc/picks/off", { ...path, body })));
  const refit = useAction(() => unwrap(api.POST("/api/characters/{character_id}/npc/picks/refit", path)));
  const named = useClanName();
  const data: PicksOut | undefined = picks.data;
  if (!data?.fitted) return null;
  const byHand = data.kept_off.length > 0 || data.pools.some((p) => p.placed.some((x) => x.by === "staff"));
  const busy = place.isPending || off.isPending || refit.isPending;

  return (
    <Card
      title="Creation picks"
      actions={
        byHand && (
          <Button variant="secondary" disabled={busy} onClick={() => refit.mutate(undefined)} className="min-h-8 px-3">
            Fit all again
          </Button>
        )
      }
    >
      <p className="mb-3 text-xs text-mist">
        Fitted to the sheet so its creation dots are free, as a player character&apos;s are. Where its player picked otherwise, set the pick here: picks set by hand stay put, and the rest fit around them.
      </p>
      <div className="flex flex-col gap-3">
        {data.pools
          .filter((pool) => pool.allowed > 0 || pool.placed.length > 0)
          .map((pool) =>
            pool.kind === "points" ? (
              <Budget key={`${pool.category}/0`} pool={pool} busy={busy} named={named} place={(b) => place.mutate(b)} off={(b) => off.mutate(b)} />
            ) : (
              <Slots key={`${pool.category}/${pool.rating}`} pool={pool} busy={busy} named={named} place={(b) => place.mutate(b)} off={(b) => off.mutate(b)} />
            ),
          )}
      </div>
      {data.kept_off.length > 0 && (
        <p className="mt-3 text-xs text-mist">Kept without a pick: {data.kept_off.map((k) => named(shown(k.name, k.detail))).join(", ")}.</p>
      )}
      <ErrorText error={place.error ?? off.error ?? refit.error} />
    </Card>
  );
}

type Props = {
  pool: PoolOut;
  busy: boolean;
  named: (name: string) => string;
  place: (body: Body) => void;
  off: (body: Body) => void;
};

function ByHand({ placed }: { placed?: Placed }) {
  return placed?.by === "staff" ? <Badge tone="gold">by hand</Badge> : null;
}

/** Picks at one rating: a choice of trait for each. */
function Slots({ pool, busy, named, place, off }: Props) {
  const label = `${pool.category_name} at ${pool.rating}`;
  // The picks placed, and one choice for those still to place, however many there are.
  const unplaced = Math.max(0, pool.allowed - pool.placed.length);
  const slots: (Placed | undefined)[] = [...pool.placed, ...(unplaced ? [undefined] : [])];
  return (
    <div>
      {/* Not a heading: each choice carries it as its own label. */}
      <p className="mb-1 text-xs tracking-wide text-mist uppercase">{label}</p>
      <ul className="flex flex-col gap-1">
        {slots.map((current, i) => (
          <li key={i} className="flex items-center gap-2">
            <Select
              aria-label={`${label}, pick ${i + 1}`}
              disabled={busy}
              value={current ? key(current.name, current.detail) : ""}
              onChange={(e) => {
                const chosen = pool.candidates.find((c) => key(c.name, c.detail) === e.target.value);
                if (chosen) {
                  place({
                    category: pool.category,
                    name: chosen.name,
                    detail: chosen.detail,
                    rating: pool.rating,
                    ...(current ? { replacing: { name: current.name, detail: current.detail } } : {}),
                  });
                } else if (current) off({ category: pool.category, name: current.name, detail: current.detail });
              }}
              className="h-8 min-w-0 flex-1 py-0 text-sm"
            >
              <option value="">{current ? "No pick (take it off)" : "Not placed"}</option>
              {current && !pool.candidates.some((c) => key(c.name, c.detail) === key(current.name, current.detail)) && (
                <option value={key(current.name, current.detail)}>{named(shown(current.name, current.detail))}</option>
              )}
              {pool.candidates.map((c) => (
                <option key={key(c.name, c.detail)} value={key(c.name, c.detail)}>
                  {named(shown(c.name, c.detail))} ({c.rating})
                </option>
              ))}
            </Select>
            <ByHand placed={current} />
            {!current && unplaced > 1 && <span className="shrink-0 text-xs text-mist">{unplaced} to place</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A budget of points (merits, flaws): the traits it pays for, and what else it could. */
function Budget({ pool, busy, named, place, off }: Props) {
  const used = pool.placed.reduce((n, p) => n + p.pick, 0);
  // Fitted ones make way for one added by hand; those placed by hand don't.
  const byHand = pool.placed.reduce((n, p) => n + (p.by === "staff" ? p.pick : 0), 0);
  const placed = new Set(pool.placed.map((p) => key(p.name, p.detail)));
  const others = pool.candidates.filter((c) => !placed.has(key(c.name, c.detail)) && c.rating <= pool.allowed - byHand);
  const label = pool.category_name;
  return (
    <div>
      <p className="mb-1 text-xs tracking-wide text-mist uppercase">
        {label}: {used} of {pool.allowed} points
      </p>
      <ul className="flex flex-col gap-1">
        {pool.placed.map((p) => (
          <li key={key(p.name, p.detail)} className="flex items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2">
              {named(shown(p.name, p.detail))} ({p.pick}) <ByHand placed={p} />
            </span>
            <Button
              variant="secondary"
              disabled={busy}
              aria-label={`Take ${p.name} off the ${label.toLowerCase()} points`}
              onClick={() => off({ category: pool.category, name: p.name, detail: p.detail })}
              className="min-h-8 px-2"
            >
              Take off
            </Button>
          </li>
        ))}
      </ul>
      {others.length > 0 && (
        <Select
          aria-label={`Add to the ${label.toLowerCase()} points`}
          disabled={busy}
          value=""
          onChange={(e) => {
            const chosen = others.find((c) => key(c.name, c.detail) === e.target.value);
            if (chosen) place({ category: pool.category, name: chosen.name, detail: chosen.detail });
          }}
          className="mt-1 h-8 py-0 text-sm"
        >
          <option value="">Add from the points…</option>
          {others.map((c) => (
            <option key={key(c.name, c.detail)} value={key(c.name, c.detail)}>
              {named(shown(c.name, c.detail))} ({c.rating})
            </option>
          ))}
        </Select>
      )}
    </div>
  );
}
