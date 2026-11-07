import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { ResponseItemIn, ResponseItemOut, WorkItemOut } from "../api/types";
import { useAction } from "../hooks";
import { EquipmentEditor, useEquipmentRules } from "../pages/troupe/EquipmentEditor";
import { NEW_ITEM, qualityChoices, qualityOf, type Draft, type Grade, type Kind } from "../pages/troupe/equipment";
import { Dialog } from "./Dialog";
import { Badge, Button, ErrorText, Field, Input, Loading, Select } from "./ui";

type Body = ResponseItemIn;

/**
 * What a response gives its character (#508): a new item, built in the Equipment tab's
 * editor, or a quality on an item the character holds. It goes when the response is
 * delivered, with the results; until then the character's home troupe's storytellers
 * and assistants change it or take it off.
 */
export function ResponseItems({ item, troupeId }: { item: WorkItemOut; troupeId: string }) {
  const [open, setOpen] = useState<"item" | "quality" | null>(null);
  const [editing, setEditing] = useState<ResponseItemOut | null>(null);
  const path = { response_id: item.id };
  const save = (body: Body) =>
    editing
      ? unwrap(api.PUT("/api/responses/{response_id}/items/{row_id}", { params: { path: { ...path, row_id: editing.id } }, body }))
      : unwrap(api.POST("/api/responses/{response_id}/items", { params: { path }, body }));
  const remove = useAction((rowId: string) => unwrap(api.DELETE("/api/responses/{response_id}/items/{row_id}", { params: { path: { ...path, row_id: rowId } } })));
  if (!item.items.length && !item.can_give) return null;
  const close = () => {
    setOpen(null);
    setEditing(null);
  };
  const change = (row: ResponseItemOut) => {
    setEditing(row);
    setOpen(row.kind === "quality" ? "quality" : "item");
  };
  const who = item.character_name;
  return (
    <section aria-label={`What ${who} receives`} className="flex flex-col gap-1 text-sm">
      {item.items.length > 0 && (
        <ul className="flex flex-col gap-1">
          {item.items.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2">
              <span>
                <span className="text-mist">{row.given_at ? "Received: " : "Gives: "}</span>
                {row.text}
              </span>
              <Badge tone={row.given_at ? "gold" : "mist"}>{row.given_at ? "Given" : "With the results"}</Badge>
              {item.can_give && !row.given_at && (
                <>
                  <Button variant="ghost" className="px-2" aria-label={`Change ${row.text}`} onClick={() => change(row)}>
                    Change
                  </Button>
                  <Button variant="ghost" className="px-2" aria-label={`Take ${row.text} off`} disabled={remove.isPending} onClick={() => remove.mutate(row.id)}>
                    Take off
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={remove.error} />
      {item.can_give && (
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setOpen("item")}>
            Give an item
          </Button>
          <Button variant="ghost" onClick={() => setOpen("quality")}>
            Add a quality
          </Button>
        </div>
      )}
      <Dialog title={editing ? `Change ${editing.text}` : `Give ${who} an item`} open={open === "item"} onClose={close} wide phoneFull>
        {open === "item" && <GiveItem key={editing?.id ?? "new"} item={item} troupeId={troupeId} editing={editing} save={save} onDone={close} />}
      </Dialog>
      <Dialog title={editing ? `Change ${editing.text}` : `Add a quality to one of ${who}'s items`} open={open === "quality"} onClose={close}>
        {open === "quality" && <AddQuality key={editing?.id ?? "new"} item={item} editing={editing} save={save} onDone={close} />}
      </Dialog>
    </section>
  );
}

function useCharacter(id: string) {
  return useQuery({
    queryKey: ["character", id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}", { params: { path: { character_id: id } } })),
  });
}

/** The Equipment tab's editor, for this character, sending the item to the response. */
function GiveItem({
  item,
  troupeId,
  editing,
  save,
  onDone,
}: {
  item: WorkItemOut;
  troupeId: string;
  editing: ResponseItemOut | null;
  save: (body: Body) => Promise<unknown>;
  onDone: () => void;
}) {
  const character = useCharacter(item.character_id);
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  if (character.error || troupe.error) return <ErrorText error={character.error ?? troupe.error} />;
  if (!character.data || !troupe.data) return <Loading />;
  const c = character.data;
  const holder = { id: c.id, name: c.name, kind: c.kind, player_name: null, splat: c.splat };
  const was = editing?.item;
  // A Beyond Your Means action (#509) asks for one item: the editor starts from it.
  const wanted = item.keyword_key === "beyond_your_means" && typeof item.structured.item === "string" ? item.structured.item : "";
  const start: { draft: Draft; template: string | null; fresh?: boolean } | undefined = was
    ? {
        draft: {
          ...NEW_ITEM,
          ...was,
          kind: was.kind as Kind,
          grade: was.grade as Grade,
          qualities: was.qualities.map((q) => ({ name: q.name, detail: q.detail ?? "" })),
          effects: was.effects.map((e) => ({ ...e })),
        },
        template: was.template ?? null,
      }
    : wanted
      ? { draft: { ...NEW_ITEM, name: wanted, kind: "miscellaneous", grade: "cheap" }, template: null, fresh: true }
      : undefined;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-mist">It goes to {c.name} when this response is delivered, with the results, and shows there as received.</p>
      <EquipmentEditor troupeId={troupeId} troupeName={troupe.data.name} holders={[holder]} holder={holder} start={start} send={(body) => save({ item: body })} onDone={onDone} />
    </div>
  );
}

/** A quality, such as Antique, Stylish or Nondescript, on an item the character holds. */
function AddQuality({ item, editing, save, onDone }: { item: WorkItemOut; editing: ResponseItemOut | null; save: (body: Body) => Promise<unknown>; onDone: () => void }) {
  const character = useCharacter(item.character_id);
  const held = useQuery({
    queryKey: ["character-equipment", item.character_id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/equipment", { params: { path: { character_id: item.character_id } } })),
  });
  const rules = useEquipmentRules(character.data?.splat ?? "vampire");
  const was = editing?.quality;
  const [itemId, setItemId] = useState(was?.item_id ?? "");
  const [name, setName] = useState(was?.name ?? "");
  const [detail, setDetail] = useState(was?.detail ?? "");
  const send = useAction(async () => {
    await save({ quality: { item_id: itemId, name, detail } });
    onDone();
  });
  if (held.error || rules.error) return <ErrorText error={held.error ?? rules.error} />;
  if (!held.data || !rules.data) return <Loading />;
  const items = held.data.items.filter((i) => i.status === "held" && i.kind !== "text");
  const chosen = items.find((i) => i.id === itemId);
  const choices = chosen ? qualityChoices(rules.data, chosen.kind as Kind, chosen.qualities) : [];
  const quality = chosen && name ? qualityOf(rules.data, chosen.kind, name) : undefined;
  if (!items.length) return <p className="text-sm text-mist">{item.character_name} holds no item that takes qualities.</p>;
  return (
    <form
      aria-label="Add a quality"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        send.mutate(undefined);
      }}
    >
      <Field label="Item">
        <Select
          value={itemId}
          onChange={(e) => {
            setItemId(e.target.value);
            setName("");
            setDetail("");
          }}
        >
          <option value="">Choose…</option>
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name}
            </option>
          ))}
        </Select>
      </Field>
      {chosen && (
        <Field label="Quality" hint={quality ? `${quality.effect}${quality.page ? ` (p. ${quality.page})` : ""}` : "It must fit the item's grade, as any quality does."}>
          <Select value={name} onChange={(e) => setName(e.target.value)}>
            <option value="">Choose…</option>
            {choices.map((q) => (
              <option key={q.name} value={q.name}>
                {q.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {(quality?.needs_detail || quality?.detail_prompt) && (
        <Field label={`${name} detail${quality.needs_detail ? "" : " (optional)"}`} hint={quality.detail_prompt ?? undefined}>
          <Input value={detail} onChange={(e) => setDetail(e.target.value)} />
        </Field>
      )}
      <p className="text-xs text-mist">It goes on the item when this response is delivered, with the results.</p>
      <ErrorText error={send.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={send.isPending || !chosen || !name}>
          {editing ? "Save changes" : "Add it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
