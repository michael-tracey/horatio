import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, EquipmentItemOut, EquipmentReceiverOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Card, ErrorText, Loading, Notice } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { ItemActions } from "./ItemActions";
import {
  combatFirst,
  factsText,
  givenText,
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
 * and where it came from. Weapons first, then armour, as on the Play View, and
 * Vampiric Texts last (#341). Its
 * player and its home troupe's staff give each item to another character, or
 * discard it (#282).
 */
export function EquipmentTab({ character }: { character: CharacterOut }) {
  const held = useCharacterEquipment(character.id);
  const [done, setDone] = useState("");
  if (held.isPending) return <Loading />;
  if (held.error) return <ErrorText error={held.error} />;
  const { items, can_give, can_pass, receivers } = held.data;
  const notice = done && <Notice>{done}</Notice>;
  if (items.length === 0)
    return (
      <div className="flex flex-col gap-3">
        {notice}
        <Card>
          <EmptyState title="No equipment yet.">
            {can_give && character.status === "active"
              ? "Give it with Give equipment, above."
              : "Your storytellers give equipment. Weapons, armour, other gear and Vampiric Texts show here once given."}
          </EmptyState>
        </Card>
      </div>
    );
  return (
    <div className="flex flex-col gap-3">
      {notice}
      <ul
        aria-label="Equipment"
        className="grid items-start gap-3 md:grid-cols-2"
      >
        {combatFirst(items).map((item) => (
          <EquipmentCard
            key={item.id}
            item={item}
            actions={
              can_pass && (
                <PassActions
                  characterId={character.id}
                  item={item}
                  receivers={receivers}
                  onDone={setDone}
                />
              )
            }
          />
        ))}
      </ul>
    </div>
  );
}

/** Give and Discard, made at once with the API. */
function PassActions({
  characterId,
  item,
  receivers,
  onDone,
}: {
  characterId: string;
  item: EquipmentItemOut;
  receivers: EquipmentReceiverOut[];
  onDone: (said: string) => void;
}) {
  const path = { character_id: characterId, item_id: item.id };
  const give = useAction(
    async ({ to, note }: { to: EquipmentReceiverOut; note: string }) => {
      await unwrap(
        api.POST("/api/characters/{character_id}/equipment/{item_id}/give", {
          params: { path },
          body: { to_character_id: to.id, note },
        }),
      );
      onDone(`Gave ${item.name} to ${to.name}.`);
    },
  );
  const discard = useAction(async (note: string) => {
    await unwrap(
      api.POST("/api/characters/{character_id}/equipment/{item_id}/discard", {
        params: { path },
        body: { note },
      }),
    );
    onDone(`Discarded ${item.name}.`);
  });
  return (
    <ItemActions
      item={item}
      receivers={receivers}
      give={(to, note) => give.mutateAsync({ to, note })}
      discard={(note) => discard.mutateAsync(note)}
    />
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
        {givenText(item)}, {dates.date(item.given_at)}
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
