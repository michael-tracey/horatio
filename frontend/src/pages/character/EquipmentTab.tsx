import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, EquipmentItemOut } from "../../api/types";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Empty, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import {
  combatFirst,
  factsText,
  kindText,
  qualityText,
} from "../troupe/equipment";

/** What a character with no equipment sees, on its page and its Play View. */
export const NO_EQUIPMENT =
  "No equipment yet. Your storytellers give equipment.";

/** What the character holds, for whoever sees its sheet (the staff note only for its home troupe's staff). */
export function useCharacterEquipment(characterId: string) {
  return useQuery({
    queryKey: ["character-equipment", characterId],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/equipment", {
          params: { path: { character_id: characterId } },
        }),
      ),
  });
}

/**
 * The character page's Equipment tab, for its player and staff who see the sheet:
 * each item with its qualities and what they do, its facts, its special effects,
 * and where it came from. Weapons first, then armour, as on the Play View.
 */
export function EquipmentTab({ character }: { character: CharacterOut }) {
  const held = useCharacterEquipment(character.id);
  if (held.isPending) return <Loading />;
  if (held.error) return <ErrorText error={held.error} />;
  const { items, can_give } = held.data;
  if (items.length === 0)
    return (
      <Empty>
        {can_give && character.status === "active"
          ? "No equipment yet. Give it with Give equipment, above."
          : NO_EQUIPMENT}
      </Empty>
    );
  return (
    <ul
      aria-label="Equipment"
      className="grid items-start gap-3 md:grid-cols-2"
    >
      {combatFirst(items).map((item) => (
        <EquipmentCard key={item.id} item={item} />
      ))}
    </ul>
  );
}

/** One item in full. `actions` go at its foot: a player's give and discard (#282). */
export function EquipmentCard({
  item,
  actions,
}: {
  item: EquipmentItemOut;
  actions?: ReactNode;
}) {
  const dates = useDates();
  const facts = factsText(item.facts);
  return (
    <li
      aria-label={item.name}
      className="flex flex-col gap-2 rounded-lg border border-ash bg-dusk p-4 text-sm"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="font-display text-base text-gold">{item.name}</h3>
          <p className="text-mist">{kindText(undefined, item)}</p>
        </div>
        {item.special && (
          <Badge tone="gold">Special, by {item.special_troupe_name}</Badge>
        )}
      </header>
      {(facts || item.facts.aggravated_against.length > 0) && (
        <p className="text-xs text-mist">
          {facts}
          {item.facts.aggravated_against.length > 0 && (
            <span className="block">
              Aggravated damage to {item.facts.aggravated_against.join("; ")}.
            </span>
          )}
        </p>
      )}
      {item.qualities.length > 0 && (
        <ul
          aria-label={`${item.name}'s qualities`}
          className="flex flex-col gap-1"
        >
          {item.qualities.map((q, i) => (
            <li key={`${q.name}/${i}`}>
              <span className="text-parchment">{qualityText(q)}</span>
              {q.effect && <span className="text-mist">: {q.effect}</span>}
              {pageLabel(q.page) && (
                <span className="block text-xs text-mist">
                  {pageLabel(q.page)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {item.effects.length > 0 && (
        <ul
          aria-label={`${item.name}'s special effects`}
          className="flex flex-col gap-1"
        >
          {item.effects.map((e) => (
            <li key={e.name}>
              <span
                className="text-gold"
                title={`${item.special_troupe_name}'s own`}
              >
                ★ {e.name}
              </span>
              <span className="text-mist">: {e.effect}</span>
            </li>
          ))}
        </ul>
      )}
      {item.description && (
        <p className="whitespace-pre-line">{item.description}</p>
      )}
      <p className="text-xs text-mist">
        Given by {item.given_by_name ?? "someone"} of {item.troupe_name},{" "}
        {dates.date(item.given_at)}
      </p>
      {item.staff_note && (
        <p className="whitespace-pre-line text-xs text-mist">
          Staff note: {item.staff_note}
        </p>
      )}
      {actions}
    </li>
  );
}
