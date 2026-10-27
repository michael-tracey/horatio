import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { EquipmentItemOut, EquipmentOut, EquipmentHolderOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { ItemActions } from "../character/ItemActions";
import { EquipmentEditor, useEquipmentRules, useTroupeTemplates } from "./EquipmentEditor";
import { factsText, kindText, qualityText, type Kind } from "./equipment";

const KINDS: { key: Kind; name: string }[] = [
  { key: "melee", name: "Melee weapons" },
  { key: "ranged", name: "Ranged weapons" },
  { key: "protective", name: "Protective gear" },
  { key: "miscellaneous", name: "Miscellaneous gear" },
];

/**
 * Every item the troupe's home characters hold, for its storytellers and
 * assistants: give one, change it, move it to another home character, discard it
 * or take it back, with filters by holder and kind. Discarded items are kept below,
 * with their history, to restore. Items go with a character whose home troupe
 * changes.
 */
export function EquipmentTab({ troupeId, troupeName }: { troupeId: string; troupeName: string }) {
  const [holder, setHolder] = useState("");
  const [kind, setKind] = useState("");
  const [giving, setGiving] = useState(false);
  const [given, setGiven] = useState("");
  const list = useQuery({
    queryKey: ["troupe-equipment", troupeId, holder, kind],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/equipment", {
          params: { path: { troupe_id: troupeId }, query: { character_id: holder || undefined, kind: (kind as Kind) || undefined } },
        }),
      ),
    placeholderData: (previous) => previous,
  });
  const discarded = useQuery({
    queryKey: ["troupe-equipment", troupeId, holder, kind, "discarded"],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/equipment", {
          params: { path: { troupe_id: troupeId }, query: { character_id: holder || undefined, kind: (kind as Kind) || undefined, status: ["discarded"] } },
        }),
      ),
    placeholderData: (previous) => previous,
  });
  const rules = useEquipmentRules("vampire");
  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const { items, characters } = list.data;

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Equipment"
        actions={
          !giving && (
            <Button
              variant="secondary"
              onClick={() => {
                setGiving(true);
                setGiven("");
              }}
            >
              Give equipment
            </Button>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">
          What {troupeName}'s home characters hold, PCs and NPCs. Only a character's home troupe gives it equipment or changes what it holds, and an item goes with its
          character wherever its home is. Weapons, protective gear and other gear, with the book's qualities (MET: VTM pp. 515–524).
        </p>
        {giving && (
          <EquipmentEditor
            troupeId={troupeId}
            troupeName={troupeName}
            holders={characters}
            onDone={(name) => {
              setGiving(false);
              setGiven(name);
            }}
          />
        )}
        {given && <Notice>Given {given}.</Notice>}
      </Card>
      <div className="flex flex-wrap gap-3">
        <div className="min-w-48 flex-1 sm:max-w-xs sm:flex-none">
          <Field label="Held by">
            <Select value={holder} onChange={(e) => setHolder(e.target.value)}>
              <option value="">Every character</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="min-w-48 flex-1 sm:max-w-xs sm:flex-none">
          <Field label="Kind">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Every kind</option>
              {KINDS.map((k) => (
                <option key={k.key} value={k.key}>
                  {k.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
      {items.length === 0 ? (
        <Empty>{holder || kind ? "No equipment matches." : "No equipment yet."}</Empty>
      ) : (
        <ul aria-label="Equipment held" className="flex flex-col gap-2">
          {items.map((item) => (
            <ItemCard key={item.id} item={item} rules={rules.data} troupeId={troupeId} troupeName={troupeName} holders={characters} />
          ))}
        </ul>
      )}
      {!!discarded.data?.items.length && (
        <Card title="Discarded">
          <p className="mb-2 text-sm text-mist">Items their players or staff discarded, kept with their history. Restore one if it was a mistake: it goes back to the character that discarded it.</p>
          <ul aria-label="Equipment discarded" className="flex flex-col gap-2">
            {discarded.data.items.map((item) => (
              <ItemCard key={item.id} item={item} rules={rules.data} troupeId={troupeId} troupeName={troupeName} holders={characters} />
            ))}
          </ul>
        </Card>
      )}
      <TroupeTemplates troupeId={troupeId} troupeName={troupeName} rules={rules.data} />
    </div>
  );
}

/** One item, with what it is and does, and staff's changes. */
function ItemCard({
  item,
  rules,
  troupeId,
  troupeName,
  holders,
}: {
  item: EquipmentItemOut;
  rules: EquipmentOut | undefined;
  troupeId: string;
  troupeName: string;
  holders: EquipmentHolderOut[];
}) {
  const dates = useDates();
  const [doing, setDoing] = useState<"" | "change" | "take" | "history">("");
  const facts = factsText(item.facts);
  const path = { character_id: item.character_id, item_id: item.id };
  const give = useAction(({ to, note }: { to: string; note: string }) =>
    unwrap(api.POST("/api/characters/{character_id}/equipment/{item_id}/give", { params: { path }, body: { to_character_id: to, note } })),
  );
  const discard = useAction((note: string) => unwrap(api.POST("/api/characters/{character_id}/equipment/{item_id}/discard", { params: { path }, body: { note } })));
  const restore = useAction(() =>
    unwrap(api.POST("/api/troupes/{troupe_id}/equipment/{item_id}/restore", { params: { path: { troupe_id: troupeId, item_id: item.id } } })),
  );
  return (
    <li aria-label={`${item.name}, held by ${item.character_name}`} className="rounded-md border border-ash bg-dusk p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="font-medium text-gold">{item.name}</span>{" "}
          <span className="text-mist">
            held by{" "}
            <Link to={`/characters/${item.character_id}`} className="hover:text-gold">
              {item.character_name}
            </Link>
            {item.character_kind === "npc" ? " (NPC)" : item.player_name ? ` (${item.player_name})` : ""}
          </span>
        </div>
        {item.special && <Badge tone="gold">Special, by {item.special_troupe_name}</Badge>}
      </div>
      <p className="mt-1">
        {kindText(rules, item)}
        {item.qualities.length > 0 && `: ${item.qualities.map(qualityText).join(", ")}`}
      </p>
      {facts && <p className="text-xs text-mist">{facts}</p>}
      {item.facts.aggravated_against.length > 0 && <p className="text-xs text-mist">Aggravated damage to {item.facts.aggravated_against.join("; ")}.</p>}
      {item.effects.length > 0 && (
        <ul aria-label={`${item.name}'s special effects`} className="mt-1 flex flex-col gap-0.5">
          {item.effects.map((e) => (
            <li key={e.name}>
              <span className="text-gold" title={`${item.special_troupe_name}'s own`}>
                ★ {e.name}
              </span>
              : {e.effect}
            </li>
          ))}
        </ul>
      )}
      {item.description && <p className="mt-1 whitespace-pre-line">{item.description}</p>}
      {item.staff_note && <p className="mt-1 whitespace-pre-line text-xs text-mist">Staff note: {item.staff_note}</p>}
      <p className="mt-1 text-xs text-mist">
        Given by {item.given_by_name ?? "someone"} of {item.troupe_name}, {dates.date(item.given_at)}
      </p>
      {item.discarded && (
        <p className="mt-1 text-sm">
          Discarded by {item.discarded.by_name ?? "someone"}, {dates.date(item.discarded.at)}
          {item.discarded.note ? `: ${item.discarded.note}` : "."}
        </p>
      )}
      {item.status === "discarded" && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={restore.isPending} onClick={() => restore.mutate(undefined)}>
            Restore to {item.character_name}
          </Button>
          <Button variant="ghost" onClick={() => setDoing(doing === "history" ? "" : "history")}>
            History
          </Button>
        </div>
      )}
      <ErrorText error={restore.error} />
      {item.can_change && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setDoing(doing === "change" ? "" : "change")}>
            Change
          </Button>
          <Button variant="secondary" onClick={() => setDoing(doing === "take" ? "" : "take")}>
            Take back
          </Button>
          <Button variant="ghost" onClick={() => setDoing(doing === "history" ? "" : "history")}>
            History
          </Button>
        </div>
      )}
      {item.can_change && (
        <div className="mt-2">
          <ItemActions
            item={item}
            receivers={holders.filter((h) => h.id !== item.character_id).map((h) => ({ ...h, title: "" }))}
            give={(to, note) => give.mutateAsync({ to: to.id, note })}
            discard={(note) => discard.mutateAsync(note)}
          />
        </div>
      )}
      {doing === "change" && (
        <div className="mt-3">
          <EquipmentEditor troupeId={troupeId} troupeName={troupeName} holders={holders} item={item} onDone={() => setDoing("")} />
        </div>
      )}
      {doing === "take" && <TakeBack troupeId={troupeId} item={item} onDone={() => setDoing("")} />}
      {doing === "history" && <History troupeId={troupeId} item={item} />}
    </li>
  );
}

function TakeBack({ troupeId, item, onDone }: { troupeId: string; item: EquipmentItemOut; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const take = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/equipment/{item_id}/take-back", {
        params: { path: { troupe_id: troupeId, item_id: item.id } },
        body: { reason },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Take back ${item.name}`}
      className="mt-3 flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        take.mutate(undefined);
      }}
    >
      <Field label="Why it is taken back" hint={`${item.character_name}'s player is told, and it goes in the character's log.`}>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={take.error} />
      <div className="flex gap-2">
        <Button type="submit" variant="danger" disabled={take.isPending || !reason.trim()}>
          Take back {item.name}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function History({ troupeId, item }: { troupeId: string; item: EquipmentItemOut }) {
  const dates = useDates();
  const detail = useQuery({
    queryKey: ["equipment-item", item.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/equipment/{item_id}", { params: { path: { troupe_id: troupeId, item_id: item.id } } })),
  });
  if (detail.isPending) return <Loading />;
  if (detail.error) return <ErrorText error={detail.error} />;
  return (
    <ol aria-label={`${item.name}'s history`} className="mt-3 flex flex-col gap-1 border-l border-ash pl-3 text-xs">
      {detail.data.history.map((e) => (
        <li key={e.id}>
          <span className="text-mist">
            {dates.dateTime(e.at)}
            {e.actor_name && `, ${e.actor_name}`}:
          </span>{" "}
          {e.summary}
          {e.reason && ` (${e.reason})`}
        </li>
      ))}
    </ol>
  );
}

/** The troupe's own templates, to start items from; saved from the editor. */
function TroupeTemplates({ troupeId, troupeName, rules }: { troupeId: string; troupeName: string; rules: EquipmentOut | undefined }) {
  const templates = useTroupeTemplates(troupeId);
  const remove = useAction((templateId: string) =>
    unwrap(api.DELETE("/api/troupes/{troupe_id}/equipment/templates/{template_id}", { params: { path: { troupe_id: troupeId, template_id: templateId } } })),
  );
  if (!templates.data?.length) return null;
  return (
    <Card title={`${troupeName}'s templates`}>
      <p className="mb-2 text-sm text-mist">Items to start from when giving equipment, beside the book's. Save one from the editor with Save as a template.</p>
      <ErrorText error={remove.error} />
      <ul className="flex flex-col gap-1 text-sm">
        {templates.data.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {t.name} <span className="text-mist">· {kindText(rules, t)}{t.qualities.length > 0 && `: ${t.qualities.map(qualityText).join(", ")}`}</span>
            </span>
            <Button variant="ghost" aria-label={`Delete the template ${t.name}`} disabled={remove.isPending} onClick={() => remove.mutate(t.id)}>
              Delete
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
