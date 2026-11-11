import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { HolderOut, HouseTraitIn, HouseTraitOut } from "../../api/types";
import { ActionMenu, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { Explainer } from "../../components/Explainer";
import { HouseMark, HouseSummary } from "../../components/HouseMark";
import { useToast } from "../../components/Toast";
import { useClanName } from "../../components/ClanNames";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { RULES_QUERY, useAction, useRulesAction } from "../../hooks";
import { EffectsEditor, HousePreview, useHousePreview } from "./HouseEffects";

const AVAILABILITY: Record<HouseTraitIn["availability"], string> = {
  staff: "Given by staff only",
  building: "Available when building for the troupe",
};

const KINDS: HouseTraitIn["kind"][] = ["General", "Clan", "Sabbat"];

type Draft = Required<Omit<HouseTraitIn, "splat">> & { splat: string };

const EMPTY: Draft = {
  category: "merits",
  name: "",
  points: 1,
  kind: "General",
  availability: "staff",
  creation_only: false,
  description: "",
  requirement: "",
  splat: "vampire",
  effects: [],
};

const draftOf = (h: HouseTraitOut): Draft => ({
  category: h.category as Draft["category"],
  name: h.name,
  points: h.points,
  kind: h.kind as Draft["kind"],
  availability: h.availability as Draft["availability"],
  creation_only: h.creation_only,
  description: h.description,
  requirement: h.requirement,
  splat: h.splat,
  effects: h.effects,
});

/**
 * The troupe's own merits and flaws. Storytellers make them, change them (for
 * everyone who holds one), archive them so no one new takes them, and delete
 * one nobody holds. What one does is its description, for the storytellers to
 * rule on at the table.
 */
export function HouseTraitsSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [editing, setEditing] = useState<HouseTraitOut | "new" | null>(null);
  const path = { params: { path: { troupe_id: troupeId } } };
  const list = useQuery({
    queryKey: ["house-traits", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/house-traits", path)),
  });
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const splats = troupe.data?.allowed_splats ?? ["vampire"];

  return (
    <div className="flex flex-col gap-6">
      <Explainer id="rules-house-traits" title="How house merits and flaws work">
        <p className="text-sm">
          A house merit or flaw is this troupe's own. It shows with a <span className="text-gold">★</span> wherever it
          appears, and only characters whose home troupe this is, or that are being built for it, can hold one; never a
          character only visiting.
        </p>
        <p className="mt-2 text-sm text-mist">
          One given by staff only is applied from a character's sheet, free or charged. One available when building is
          picked and priced like a merit from the book. A change applies to everyone who holds it, and XP already spent
          stays as it was.
        </p>
        <p className="mt-2 text-sm text-mist">
          What one does on the sheet is its effects: free dots, a higher maximum, an XP price, an extra in-clan
          discipline, health levels, or what it requires. Each works as the book merit it copies does, and a line saying
          what it does shows under its description. One with no effects does what its description says, for you to rule
          on at the table.
        </p>
      </Explainer>

      <Dialog
        title={editing === "new" ? "A new house merit or flaw" : editing ? `Change ${editing.name}` : ""}
        open={editing !== null}
        onClose={() => setEditing(null)}
        wide
        phoneFull
      >
        {editing && <HouseTraitEditor troupeId={troupeId} editing={editing} splats={splats} onClose={() => setEditing(null)} />}
      </Dialog>

      <Card
        title="House merits and flaws"
        actions={
          canEdit && (
            <Button variant="secondary" onClick={() => setEditing("new")}>
              Add a merit or flaw
            </Button>
          )
        }
      >
        {list.data.length === 0 ? (
          <EmptyState title="The troupe has no merits or flaws of its own yet.">
            {canEdit ? "Make one with Add a merit or flaw, above. It shows on sheets with a ★." : "Its storytellers make them; each shows on sheets with a ★."}
          </EmptyState>
        ) : (
          <table aria-label="House merits and flaws" className="w-full text-sm">
            {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
            <thead className="max-lg:sr-only">
              <tr className="border-b border-ash text-left text-xs text-mist">
                <th className="py-2 pr-3 font-normal">Name</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Merit or flaw</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Points</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Availability</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Creation only</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Status</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Held by</th>
                {canEdit && (
                  <th className="py-2 font-normal">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {list.data.map((h) => (
                <HouseTraitRow key={h.id} trait={h} troupeId={troupeId} canEdit={canEdit} onChange={() => setEditing(h)} />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

/** "General merit", "Clan flaw". */
const kindText = (h: HouseTraitOut) => `${h.kind} ${h.category === "flaws" ? "flaw" : "merit"}`;

/** One house merit or flaw: what it is, what it says and does, and what staff can do with it behind ⋯. */
function HouseTraitRow({ trait: h, troupeId, canEdit, onChange }: { trait: HouseTraitOut; troupeId: string; canEdit: boolean; onChange: () => void }) {
  const named = useClanName();
  const [deleting, setDeleting] = useState(false);
  const toast = useToast();
  const path = { params: { path: { troupe_id: troupeId, house_trait_id: h.id } } };
  const archive = useRulesAction(() => unwrap(api.PUT("/api/troupes/{troupe_id}/house-traits/{house_trait_id}/archived", { ...path, body: { archived: !h.archived } })));
  // Said and closed before the list is asked again, which takes the row away.
  const remove = useRulesAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/house-traits/{house_trait_id}", path));
    toast({ message: `${h.name} deleted.` });
    setDeleting(false);
  });
  const staffOnly = h.availability === "staff";
  const held = h.holders === 1 ? "held by 1" : `held by ${h.holders}`;
  return (
    <tr>
      <td className="py-2.5 pr-3 align-top">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={h.archived ? "text-mist" : "text-parchment"}>
            {h.name}
            <HouseMark label={h.label} short summary={h.summary} />
          </span>
          {h.archived && (
            <Badge className="lg:hidden">Archived</Badge>
          )}
        </span>
        <span className="mt-0.5 block text-xs text-mist lg:hidden">
          {[kindText(h), h.points === 1 ? "1 point" : `${h.points} points`, staffOnly ? "staff only" : "players", h.creation_only && "creation only", held]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {(h.description || h.requirement) && (
          <span className="mt-0.5 block text-xs text-mist">
            {h.requirement && <span>Requires {named(h.requirement)}. </span>}
            {named(h.description)}
          </span>
        )}
        <HouseSummary summary={h.summary} />
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top whitespace-nowrap text-mist`}>{kindText(h)}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{h.points}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>
        <Badge tone={staffOnly ? "gold" : "mist"}>{staffOnly ? "Staff only" : "Players"}</Badge>
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{h.creation_only ? "Yes" : ""}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{h.archived ? <Badge>Archived</Badge> : <span className="text-mist">Active</span>}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{h.holders}</td>
      {canEdit && (
        <td className="w-px py-1 text-right align-top">
          <ActionMenu label={`Actions for ${h.name}`} variant="ghost">
            <MenuItem onSelect={onChange}>Change…</MenuItem>
            <MenuItem onSelect={() => archive.mutate(undefined)}>{h.archived ? "Bring back" : "Archive"}</MenuItem>
            {h.holders === 0 ? (
              <MenuItem danger onSelect={() => setDeleting(true)}>
                Delete…
              </MenuItem>
            ) : (
              <MenuItem disabled>
                Delete…
                <span className="block text-xs">
                  {h.holders === 1 ? "A character holds it" : `${h.holders} characters hold it`}: archive it instead.
                </span>
              </MenuItem>
            )}
          </ActionMenu>
          <ErrorText error={archive.error} />
          {/* The dialog sits here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
          <Dialog title={`Delete ${h.name}`} open={deleting} onClose={() => setDeleting(false)}>
            <p className="text-sm">No one holds it, so it goes for good.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
                Delete {h.name}
              </Button>
              <Button variant="ghost" onClick={() => setDeleting(false)}>
                Cancel
              </Button>
            </div>
            <ErrorText error={remove.error} />
          </Dialog>
        </td>
      )}
    </tr>
  );
}

function HouseTraitEditor({
  troupeId,
  editing,
  splats,
  onClose,
}: {
  troupeId: string;
  editing: HouseTraitOut | "new";
  splats: string[];
  onClose: () => void;
}) {
  const start = editing === "new" ? EMPTY : draftOf(editing);
  const [draft, setDraft] = useState<Draft>(start);
  const [confirming, setConfirming] = useState<HolderOut[] | null>(null);
  const [sample, setSample] = useState("");
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft({ ...draft, [key]: value });
  const body: HouseTraitIn = { ...draft, creation_only: draft.availability === "building" && draft.creation_only };
  const catalogue = useQuery({
    queryKey: ["catalogue", draft.splat, troupeId],
    meta: RULES_QUERY,
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: draft.splat }, query: { troupe_id: troupeId } } })),
  });
  const choices = useQuery({
    queryKey: ["house-trait-choices", troupeId, draft.splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/house-traits/choices", { params: { path: { troupe_id: troupeId }, query: { splat: draft.splat } } })),
  });
  const preview = useHousePreview(troupeId, body, editing === "new" ? null : editing.id, sample);
  const problems = new Map((preview.data?.problems ?? []).map((p) => [p.index, p.message] as const));

  const save = useRulesAction(async () => {
    if (editing === "new") {
      await unwrap(api.POST("/api/troupes/{troupe_id}/house-traits", { params: { path: { troupe_id: troupeId } }, body }));
    } else {
      await unwrap(
        api.PUT("/api/troupes/{troupe_id}/house-traits/{house_trait_id}", {
          params: { path: { troupe_id: troupeId, house_trait_id: editing.id } },
          body,
        }),
      );
    }
    onClose();
  });
  // Before a change, who it changes: a house trait is the troupe's rule, for all who hold it.
  const ask = useAction(async () => {
    if (editing === "new") return save.mutate(undefined);
    const holders = await unwrap(
      api.GET("/api/troupes/{troupe_id}/house-traits/{house_trait_id}/holders", {
        params: { path: { troupe_id: troupeId, house_trait_id: editing.id } },
      }),
    );
    if (holders.length === 0) return save.mutate(undefined);
    setConfirming(holders);
  });
  const noun = draft.category === "flaws" ? "flaw" : "merit";

  return (
    <>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          ask.mutate(undefined);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input value={draft.name} maxLength={100} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Merit or flaw">
            <Select value={draft.category} onChange={(e) => set("category", e.target.value as Draft["category"])}>
              <option value="merits">Merit</option>
              <option value="flaws">Flaw</option>
            </Select>
          </Field>
          <Field label="Points">
            <Select value={draft.points} onChange={(e) => set("points", Number(e.target.value))}>
              {[1, 2, 3, 4, 5, 6, 7].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Type" hint="For the merit limit and the filters.">
            <Select value={draft.kind} onChange={(e) => set("kind", e.target.value as Draft["kind"])}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </Select>
          </Field>
          {splats.length > 1 && (
            <Field label="For">
              <Select value={draft.splat} onChange={(e) => set("splat", e.target.value)}>
                {splats.map((s) => (
                  <option key={s} value={s}>
                    {s[0]!.toUpperCase() + s.slice(1)} characters
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Requirement" hint="Who it is for, in your words; shown with it.">
            <Input value={draft.requirement} maxLength={200} onChange={(e) => set("requirement", e.target.value)} />
          </Field>
        </div>
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1 text-sm text-mist">Who can take it</legend>
          {(Object.keys(AVAILABILITY) as Draft["availability"][]).map((a) => (
            <label key={a} className="flex items-center gap-2">
              <input type="radio" name="availability" checked={draft.availability === a} onChange={() => set("availability", a)} />
              {AVAILABILITY[a]}
            </label>
          ))}
          {draft.availability === "building" && (
            <label className="ml-6 flex items-center gap-2">
              <input type="checkbox" checked={draft.creation_only} onChange={(e) => set("creation_only", e.target.checked)} />
              Only during character creation
            </label>
          )}
        </fieldset>
        <Field label="Description" hint={`What the ${noun} does: players see it wherever it shows.`}>
          <Textarea rows={4} value={draft.description} maxLength={4000} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <EffectsEditor
          blocks={draft.effects}
          catalogue={catalogue.data}
          choices={choices.data}
          self={{ category: draft.category, name: draft.name.trim() }}
          problems={problems}
          onChange={(effects) => set("effects", effects)}
        />
        <ErrorText error={catalogue.error ?? choices.error} />
        <HousePreview preview={preview.data} error={preview.error} characterId={sample} onCharacter={setSample} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!draft.name.trim() || save.isPending || ask.isPending}>
            {editing === "new" ? `Add the ${noun}` : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>
        <ErrorText error={ask.error ?? save.error} />
      </form>
      <Dialog title={`Change ${editing === "new" ? "" : editing.name} for everyone?`} open={confirming !== null} onClose={() => setConfirming(null)}>
        <p className="text-sm">
          {confirming?.length === 1 ? "This character holds it" : `These ${confirming?.length} characters hold it`}, and the
          change applies to {confirming?.length === 1 ? "it" : "them all"}. XP already spent on it stays as it was.
        </p>
        <ul className="my-3 list-disc pl-5 text-sm">
          {confirming?.map((h) => (
            <li key={h.character_id}>
              {h.name}
              {h.kind === "npc" && <span className="text-mist"> (NPC)</span>}
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Button
            onClick={() => {
              setConfirming(null);
              save.mutate(undefined);
            }}
          >
            Change it for {confirming?.length === 1 ? "them" : "everyone"}
          </Button>
          <Button variant="ghost" onClick={() => setConfirming(null)}>
            Cancel
          </Button>
        </div>
      </Dialog>
    </>
  );
}
