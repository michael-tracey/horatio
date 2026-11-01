import type { FeedingCardOut, FeedingIn, MyDowntime, MyFeedingOut } from "../../api/types";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";

const HUNT_WORDS: Record<string, string> = { win: "a win: 3 cards", tie: "a tie: 2 cards", lose: "a loss: 1 card" };

/** The groups of cards a character sees, in the order it would look: its own first, then the Rack, then poaching. */
export function cardGroups(feeding: MyFeedingOut): { title: string; note?: string; cards: FeedingCardOut[] }[] {
  const mine = new Set(feeding.territories.filter((t) => t.mine).map((t) => t.id));
  const open = feeding.cards.filter((c) => !c.mine);
  const groups = [
    { title: "Your Herd", note: "Dealt to you, one for each dot of Herd.", cards: open.filter((c) => c.source === "herd") },
    { title: "Hunting outside the Rack", cards: open.filter((c) => c.source === "hunt") },
    { title: "Your territories", cards: open.filter((c) => c.source === "territory" && mine.has(c.territory_id ?? "")) },
    { title: "On the Rack", cards: open.filter((c) => c.source === "rack") },
    {
      title: "Other territories",
      note: "Feeding here is poaching: their holders may be patrolling.",
      cards: open.filter((c) => c.source === "territory" && !mine.has(c.territory_id ?? "")),
    },
  ];
  return groups.filter((g) => g.cards.length);
}

function CardText({ card }: { card: FeedingCardOut }) {
  return (
    <span>
      <strong className="text-gold">{card.number}</strong> · {card.resonance}
      {card.dyscrasia ? (
        <>
          {" "}
          · <strong>{card.dyscrasia}</strong>: <span className="text-mist">{card.dyscrasia_summary}</span>
        </>
      ) : (
        <span className="text-mist"> · no Dyscrasia</span>
      )}
      {card.descriptor && <span className="block text-xs text-mist">{card.descriptor}</span>}
      {card.territory_name && <span className="block text-xs text-mist">{card.territory_name}</span>}
    </span>
  );
}

/**
 * With the Rack (Vol. 2, pp. 298-303): the character takes one vessel, a Feeding
 * Card, first come, first served, in place of spending feeding actions. Taking one
 * saves at once, so no one else can take it.
 */
export function RackFeeding({ feeding, characterId, onDowntime }: { feeding: MyFeedingOut; characterId: string; onDowntime: (saved: MyDowntime) => void }) {
  const path = { params: { path: { character_id: characterId } } };
  const take = useAction(async (card_id: string | null) => onDowntime(await unwrap(api.POST("/api/characters/{character_id}/downtime/vessel", { ...path, body: { card_id } }))));
  const hunt = useAction(async () => onDowntime(await unwrap(api.POST("/api/characters/{character_id}/downtime/hunt", path))));
  const taken = feeding.cards.find((c) => c.mine);
  const locked = feeding.locked;
  const groups = cardGroups(feeding);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-mist">Take one vessel from the Rack, first come, first served. It stands in for feeding actions, and its Resonance comes with it.</p>
      {feeding.restriction && <p className="text-sm">Your feeding restriction: {feeding.restriction}. Your Herd's cards always suit you.</p>}
      <div role="status" className={`text-sm ${taken ? "text-gold" : "text-mist"}`}>
        {taken ? (
          <span className="flex flex-wrap items-start justify-between gap-2">
            <span>
              Your vessel: <CardText card={taken} />
            </span>
            {!locked && (
              <Button variant="ghost" disabled={take.isPending} onClick={() => take.mutate(null)}>
                Give it back
              </Button>
            )}
          </span>
        ) : (
          "No vessel yet: you'll come to game at half Blood unless staff say otherwise."
        )}
      </div>
      {!locked &&
        groups.map((g) => (
          <section key={g.title} aria-label={g.title} className="border-t border-ash pt-2">
            <h3 className="text-xs tracking-wide text-mist uppercase">{g.title}</h3>
            {g.note && <p className="text-xs text-mist">{g.note}</p>}
            <ul className="mt-1 flex flex-col divide-y divide-ash">
              {g.cards.map((c) => (
                <li key={c.id} className="flex items-start justify-between gap-3 py-2 text-sm" aria-label={`Feeding Card ${c.number}`}>
                  <CardText card={c} />
                  {c.suits ? (
                    <Button variant="secondary" className="shrink-0" disabled={take.isPending} onClick={() => take.mutate(c.id)}>
                      {taken ? "Take instead" : "Take"}
                    </Button>
                  ) : (
                    <span className="shrink-0 text-xs text-mist">Not for you</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      {!locked && !feeding.hunt && (
        <div className="border-t border-ash pt-2 text-sm">
          <Button variant="secondary" disabled={hunt.isPending} onClick={() => hunt.mutate(undefined)}>
            Hunt outside the Rack
          </Button>
          <p className="mt-1 text-xs text-mist">Once a cycle, if nothing here suits you: a simple challenge deals you 3 cards to choose from on a win, 2 on a tie, 1 on a loss (p. 303).</p>
        </div>
      )}
      {feeding.hunt && <p className="text-xs text-mist">You hunted outside the Rack: {HUNT_WORDS[feeding.hunt] ?? feeding.hunt}.</p>}
      <ErrorText error={take.error ?? hunt.error} />
    </div>
  );
}

/** With feeding territories and book feeding: the territory the character feeds in, once a cycle, standing in for a feeding action. */
export function TerritoryChoice({ feeding, value, onChange }: { feeding: MyFeedingOut; value: FeedingIn; onChange: (value: FeedingIn) => void }) {
  if (!feeding.territories.length) return null;
  const chosen = feeding.territories.find((t) => t.id === value.territory);
  const poaching = chosen && !chosen.mine;
  return (
    <div className="mt-3 sm:max-w-sm">
      <Field
        label="Feed in a territory"
        hint={
          poaching
            ? `That is poaching: ${chosen.holders.length ? `${chosen.holders.join(", ")} may be patrolling it` : "if anyone holds it, they may be patrolling it"}.`
            : "Once a cycle, it stands in for a feeding action (Vol. 2, pp. 304-305)."
        }
      >
        <Select disabled={feeding.locked} value={value.territory ?? ""} onChange={(e) => onChange({ ...value, territory: e.target.value })}>
          <option value="">No territory</option>
          {feeding.territories.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.mine ? "yours" : t.holders.length ? `held by ${t.holders.join(", ")}` : t.held_by ? `held by ${t.held_by}` : "unassigned"})
            </option>
          ))}
        </Select>
      </Field>
    </div>
  );
}

/** With feeding territories: downtime actions patrolling the territories the character holds, each a simple challenge against anyone poaching there. */
export function Patrols({ feeding, value, onChange, actionsLeft }: { feeding: MyFeedingOut; value: FeedingIn; onChange: (value: FeedingIn) => void; actionsLeft: number }) {
  const mine = feeding.territories.filter((t) => t.mine);
  if (!mine.length) return null;
  const patrols = value.patrols ?? [];
  const actions = (id: string) => patrols.find((p) => p.territory_id === id)?.actions ?? 0;
  const set = (id: string, n: number) => onChange({ ...value, patrols: [...patrols.filter((p) => p.territory_id !== id), { territory_id: id, actions: n }].filter((p) => p.actions) });
  return (
    <div className="mt-3 grid gap-3 border-t border-ash pt-3 sm:grid-cols-2">
      {mine.map((t) => (
        <Field key={t.id} label={`Actions patrolling ${t.name}`} hint={`From your downtime actions (${actionsLeft} left). Each one tests anyone poaching there (p. 305).`}>
          <Input
            type="number"
            min={0}
            max={actions(t.id) + Math.max(0, actionsLeft)}
            disabled={feeding.locked}
            value={actions(t.id)}
            onChange={(e) => set(t.id, Math.max(0, Number(e.target.value) || 0))}
          />
        </Field>
      ))}
    </div>
  );
}
