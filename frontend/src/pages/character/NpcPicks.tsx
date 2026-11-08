import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, NpcPicksOut as PicksOut, NpcPoolOut as PoolOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Badge, Button, Card, ErrorText, Rating, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { seatPicks } from "./creation/logic";
import { ExtraPick, Slot, SlotRows, oneOf, type Choice } from "./creation/Slots";

type Placed = PoolOut["placed"][number];
type Body = { category: string; name: string; detail: string; rating?: number; replacing?: { name: string; detail: string } };

const key = (name: string, detail: string) => (detail ? `${name}\u0000${detail}` : name);
const shown = (name: string, detail: string) => (detail ? `${name}: ${detail}` : name);

/**
 * An NPC built without the wizard has its creation picks fitted to its sheet, so its
 * creation dots are free as a player character's are (#527). Staff put the fitting
 * right where the player picked otherwise: a pick placed by hand stays, one taken off
 * a trait stays off, and the rest are fitted around them. The picks show in the
 * wizard's slots, a row for each rating.
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
  const shownPools = data.pools.filter((pool) => pool.allowed > 0 || pool.placed.length > 0);
  // Each category's picks together, a row for each rating, in the order the API gives.
  const categories = [...new Set(shownPools.filter((p) => p.kind === "picks").map((p) => p.category))];

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
        Fitted to the sheet so its creation dots are free, as a player character&apos;s are. Where its player picked otherwise, set the pick here: picks set by hand stay put, and the rest fit around them. An empty slot is a pick the fitting found no trait for.
      </p>
      <div className="flex flex-col gap-5">
        {categories.map((category) => (
          <PickSlots
            key={category}
            pools={shownPools.filter((p) => p.category === category)}
            busy={busy}
            named={named}
            place={(b) => place.mutate(b)}
            off={(b) => off.mutate(b)}
          />
        ))}
        {shownPools
          .filter((pool) => pool.kind === "points")
          .map((pool) => (
            <Budget key={pool.category} pool={pool} busy={busy} named={named} place={(b) => place.mutate(b)} off={(b) => off.mutate(b)} />
          ))}
      </div>
      {data.kept_off.length > 0 && (
        <p className="mt-3 text-xs text-mist">Kept without a pick: {data.kept_off.map((k) => named(shown(k.name, k.detail))).join(", ")}.</p>
      )}
      <ErrorText error={place.error ?? off.error ?? refit.error} />
    </Card>
  );
}

type Actions = {
  busy: boolean;
  named: (name: string) => string;
  place: (body: Body) => void;
  off: (body: Body) => void;
};

/**
 * One category's picks in the wizard's slots. Choosing a trait in a slot places it
 * there by hand; one picked at another rating moves, and one placed by hand in the
 * slot goes where it was, if it can (horatio.npc_picks.pin). Clearing a slot takes
 * the pick off its trait.
 */
function PickSlots({ pools, busy, named, place, off }: Actions & { pools: PoolOut[] }) {
  const title = pools[0]!.category_name;
  const category = pools[0]!.category;
  // Where each pick sits, by rating, so placing one doesn't shuffle the rest.
  const [seats, setSeats] = useState<Record<number, (string | null)[]>>({});
  // What a move did that wasn't asked for, under the slot it was made in.
  const [said, setSaid] = useState<{ rating: number; slot: number; text: string } | null>(null);
  const where = new Map(pools.flatMap((pool) => pool.placed.map((p) => [key(p.name, p.detail), { pool, placed: p }] as const)));
  const layout = Object.fromEntries(
    pools.map((pool) => [pool.rating, seatPicks(seats[pool.rating] ?? [], pool.placed.map((p) => key(p.name, p.detail)), pool.allowed)]),
  ) as Record<number, (string | null)[]>;
  const one = oneOf(title);

  const choose = (pool: PoolOut, slot: number, holder: string | null, value: string) => {
    const chosen = pool.candidates.find((c) => key(c.name, c.detail) === value);
    if (!chosen) return;
    const from = where.get(value)?.pool.rating;
    const current = holder ? where.get(holder)?.placed : undefined;
    const next = { ...layout, [pool.rating]: layout[pool.rating]!.map((k, i) => (i === slot ? value : k)) };
    // One placed by hand goes where the moved pick was, if it can take a pick there.
    const swaps = !!current && current.by === "staff" && from !== undefined && pools.some((p) => p.rating === from && p.candidates.some((c) => key(c.name, c.detail) === holder));
    if (from !== undefined) next[from] = (layout[from] ?? []).map((k) => (k === value ? (swaps ? holder : null) : k));
    setSeats(next);
    setSaid(
      current?.by === "staff" && from !== undefined && !swaps
        ? { rating: pool.rating, slot, text: `${named(shown(current.name, current.detail))} can't take a pick at ${from}, so it is fitted with the rest.` }
        : null,
    );
    place({
      category,
      name: chosen.name,
      detail: chosen.detail,
      rating: pool.rating,
      ...(current ? { replacing: { name: current.name, detail: current.detail } } : {}),
    });
  };
  const takeOff = (placed: Placed) => {
    setSaid(null);
    off({ category, name: placed.name, detail: placed.detail });
  };

  /** What a slot in `pool` holding `holder` offers: the traits a pick there could go on. */
  const options = (pool: PoolOut, holder: string | null): Choice[] =>
    pool.candidates.flatMap((c): Choice[] => {
      const k = key(c.name, c.detail);
      const at = where.get(k)?.pool.rating;
      // One in this row's other slots stays where it is.
      if (k !== holder && at === pool.rating) return [];
      return [
        {
          value: k,
          name: c.name,
          label: named(shown(c.name, c.detail)),
          at: k !== holder ? at : undefined,
          group: null,
          current: k === holder,
          disabled: false,
          hint: (
            <>
              rated <Rating value={c.rating} of={c.rating} className="text-xs" />
            </>
          ),
        },
      ];
    });

  const widest = Math.max(1, ...pools.map((p) => p.rating));
  return (
    <SlotRows
      title={title}
      label={`${title} picks`}
      widest={widest}
      rows={pools
        .filter((pool) => pool.kind === "picks")
        .map((pool) => ({
          rating: pool.rating,
          slots: layout[pool.rating]!.map((k, i) => {
            const placed = k ? where.get(k)?.placed : undefined;
            const label = placed ? named(shown(placed.name, placed.detail)) : "";
            if (i >= pool.allowed) {
              return (
                <ExtraPick key={`extra-${k}`} value={label} pick={k!} clearLabel={`Take ${placed!.name} off`} onClear={() => takeOff(placed!)}>
                  No pick at {pool.rating} for it now.
                </ExtraPick>
              );
            }
            return (
              <Slot
                key={`slot-${i}`}
                label={`${title} at ${pool.rating}${pool.allowed > 1 ? `, pick ${i + 1} of ${pool.allowed}` : ""}`}
                placeholder={`Choose ${one}`}
                value={label}
                choices={options(pool, k)}
                onChoose={(value) => choose(pool, i, k, value)}
                onClear={placed ? () => takeOff(placed) : undefined}
                clearLabel={placed ? `Take ${placed.name} off` : undefined}
                pick={k}
                disabled={busy}
              >
                {placed?.by === "staff" && (
                  <span className="self-start">
                    <ByHand placed={placed} />
                  </span>
                )}
                {said?.rating === pool.rating && said.slot === i && <p className="text-xs text-mist">{said.text}</p>}
              </Slot>
            );
          }),
        }))}
    />
  );
}

type Props = Actions & { pool: PoolOut };

function ByHand({ placed }: { placed?: Placed }) {
  return placed?.by === "staff" ? <Badge tone="gold">by hand</Badge> : null;
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
