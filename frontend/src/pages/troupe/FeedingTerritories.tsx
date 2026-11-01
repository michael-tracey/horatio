import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TerritoryOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";

type Size = TerritoryOut["size"];
type Draft = { name: string; size: Size; area: string; held_by: string; holder_ids: string[] };

export const SIZES: { value: Size; label: string; vessels: number; usual: string }[] = [
  { value: "small", label: "Small", vessels: 2, usual: "1 to 2" },
  { value: "moderate", label: "Moderate", vessels: 4, usual: "2 to 3" },
  { value: "notable", label: "Notable", vessels: 6, usual: "4 to 5" },
  { value: "significant", label: "Significant", vessels: 8, usual: "5 to 7" },
  { value: "large", label: "Large", vessels: 10, usual: "6 to 8" },
];

const EMPTY: Draft = { name: "", size: "small", area: "", held_by: "", holder_ids: [] };

/**
 * The troupe's feeding territories (Vol. 2, pp. 304-305): areas only the vampires the
 * domain's Authority names may feed in, rated Small to Large. Running staff keep the
 * list as the Authority proclaims it; a territory revoked or lost leaves the list.
 */
export function FeedingTerritories({ troupeId, canManage }: { troupeId: string; canManage: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const list = useQuery({ queryKey: ["feeding-territories", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/feeding-territories", path)) });
  const [editing, setEditing] = useState<{ id: string | null; draft: Draft } | null>(null);
  const toast = useToast();
  const roster = useQuery({
    queryKey: ["roster", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", path)),
    enabled: editing !== null,
  });
  const save = useAction(async ({ id, draft }: { id: string | null; draft: Draft }) => {
    if (id) await unwrap(api.PUT("/api/troupes/{troupe_id}/feeding-territories/{territory_id}", { params: { path: { troupe_id: troupeId, territory_id: id } }, body: draft }));
    else await unwrap(api.POST("/api/troupes/{troupe_id}/feeding-territories", { ...path, body: draft }));
    setEditing(null);
    toast({ message: id ? `Saved ${draft.name}.` : `Added ${draft.name}.` });
  });
  const remove = useAction(async (t: TerritoryOut) => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/feeding-territories/{territory_id}", { params: { path: { troupe_id: troupeId, territory_id: t.id } } }));
    setEditing(null);
    toast({ message: `${t.name} is off the list.` });
  });
  const home = (roster.data ?? []).filter((c) => c.home);
  const size = editing && SIZES.find((s) => s.value === editing.draft.size);
  const set = (change: Partial<Draft>) => editing && setEditing({ ...editing, draft: { ...editing.draft, ...change } });

  return (
    <Card
      title="Feeding territories"
      actions={
        canManage &&
        editing === null && (
          <Button variant="secondary" className="min-h-8 px-3" onClick={() => setEditing({ id: null, draft: EMPTY })}>
            Add a territory
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Areas where only the characters the domain's Authority names may feed. Everyone in the troupe can see them, as the domain knows them. Feeding in one stands in for a feeding
        action, or with the Rack, it has cards of its own; feeding in another's is poaching.
      </p>
      {list.data?.length === 0 && editing === null && <EmptyState title="No feeding territories yet.">{canManage && "Add one as the Authority proclaims it."}</EmptyState>}
      <ul className="flex flex-col divide-y divide-ash text-sm">
        {(list.data ?? []).map((t) => (
          <li key={t.id} className="flex items-start justify-between gap-2 py-2">
            <span>
              <strong>{t.name}</strong>
              <span className="text-mist">
                {" "}
                · {t.size_name}, {t.vessels} vessels{t.area && ` · ${t.area}`}
              </span>
              <span className="block text-mist">
                {t.holders.length ? `Held by ${t.holders.join(", ")}` : "Unassigned"}
                {t.held_by && ` (${t.held_by})`}
              </span>
            </span>
            {canManage && editing === null && (
              <Button
                variant="ghost"
                aria-label={`Change ${t.name}`}
                onClick={() => setEditing({ id: t.id, draft: { name: t.name, size: t.size, area: t.area, held_by: t.held_by, holder_ids: t.holder_ids } })}
              >
                Change
              </Button>
            )}
          </li>
        ))}
      </ul>
      {editing && (
        <form
          className="mt-3 flex flex-col gap-3 border-t border-ash pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(editing);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name">
              <Input value={editing.draft.name} onChange={(e) => set({ name: e.target.value })} />
            </Field>
            <Field label="Size" hint={size && `${size.vessels} vessels; usually ${size.usual} vampires (p. 304).`}>
              <Select value={editing.draft.size} onChange={(e) => set({ size: e.target.value as Size })}>
                {SIZES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Where it is">
              <Input value={editing.draft.area} placeholder="Optional" onChange={(e) => set({ area: e.target.value })} />
            </Field>
            <Field label="Proclaimed for" hint="In the proclamation's words: a clan, a pack, an officer.">
              <Input value={editing.draft.held_by} placeholder="Optional" onChange={(e) => set({ held_by: e.target.value })} />
            </Field>
          </div>
          <fieldset className="flex flex-col gap-1 text-sm">
            <legend className="mb-1 text-mist">Characters who may feed there</legend>
            {roster.isPending && <span className="text-mist">Loading…</span>}
            <div className="grid gap-1 sm:grid-cols-2">
              {home.map((c) => (
                <label key={c.character_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={editing.draft.holder_ids.includes(c.character_id)}
                    onChange={(e) =>
                      set({ holder_ids: e.target.checked ? [...editing.draft.holder_ids, c.character_id] : editing.draft.holder_ids.filter((i) => i !== c.character_id) })
                    }
                  />
                  {c.character_name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending || !editing.draft.name.trim()}>
              {editing.id ? "Save" : "Add"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            {editing.id && (
              <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(list.data!.find((t) => t.id === editing.id)!)}>
                Revoke it
              </Button>
            )}
          </div>
          <ErrorText error={save.error ?? remove.error ?? roster.error} />
        </form>
      )}
      <ErrorText error={list.error} />
    </Card>
  );
}
