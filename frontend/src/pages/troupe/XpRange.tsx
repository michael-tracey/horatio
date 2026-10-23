import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Field, Input } from "../../components/ui";
import { useAction } from "../../hooks";
import { makeUp } from "./xpRange";

const KINDS: Record<string, string> = { game: "Game", downtime: "Downtime", set: "Set by hand" };

/**
 * The troupe's XP floor and ceiling: the least and most a character here could
 * have been given by now. A character built for the troupe starts at the floor.
 * Storytellers can set either by hand, for a chronicle that began before Horatio.
 */
export function XpRangeCard({ troupeId, canEdit, link }: { troupeId: string; canEdit: boolean; link?: ReactNode }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const range = useQuery({ queryKey: ["xp-range", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/xp-range", path)) });
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ floor: 0, ceiling: 0, reason: "" });
  const [showAll, setShowAll] = useState(false);
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/xp-range", { ...path, body: form }));
    setEditing(false);
  });
  if (!range.data) return <ErrorText error={range.error} />;
  const r = range.data;
  const words = makeUp(r);
  const entries = showAll ? r.entries : r.entries.slice(0, 5);

  return (
    <Card
      title="XP floor and ceiling"
      actions={
        <span className="flex flex-wrap items-center gap-2">
          {link}
          {canEdit && !editing && (
            <Button
              variant="ghost"
              className="min-h-8 px-2"
              onClick={() => {
                setForm({ floor: r.floor, ceiling: r.ceiling, reason: "" });
                setEditing(true);
              }}
            >
              Set by hand
            </Button>
          )}
        </span>
      }
    >
      <p className="mb-3 text-sm text-mist">
        The ceiling is the most XP a character here could have by now: the starting XP, every game's XP and every downtime's XP. The floor leaves out
        the downtimes. New characters built for this troupe start at the floor.
      </p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-mist">Floor</dt>
        <dd>
          <span className="font-mono">{r.floor} XP</span> <span className="text-xs text-mist">({words.floor})</span>
        </dd>
        <dt className="text-mist">Ceiling</dt>
        <dd>
          <span className="font-mono">{r.ceiling} XP</span> <span className="text-xs text-mist">({words.ceiling})</span>
        </dd>
      </dl>
      {editing && (
        <form
          className="mt-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <Field label="Floor">
            <Input type="number" min={0} required value={form.floor} onChange={(e) => setForm({ ...form, floor: Number(e.target.value) })} className="w-24" />
          </Field>
          <Field label="Ceiling">
            <Input type="number" min={0} required value={form.ceiling} onChange={(e) => setForm({ ...form, ceiling: Number(e.target.value) })} className="w-24" />
          </Field>
          <div className="min-w-48 flex-1">
            <Field label="Why">
              <Input required maxLength={500} placeholder="Chronicle began in 2019" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
            </Field>
          </div>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <p className="w-full text-xs text-mist">Games and downtimes still add to them afterwards.</p>
          <ErrorText error={save.error} />
        </form>
      )}
      {r.entries.length > 0 && (
        <>
          <h3 className="mt-4 mb-1 font-sans text-xs text-mist uppercase">What changed them</h3>
          <ul className="divide-y divide-ash text-sm">
            {entries.map((e) => (
              <li key={e.id} className="flex flex-wrap justify-between gap-2 py-1.5">
                <span>
                  <span className="mr-2 text-xs whitespace-nowrap text-mist">{e.entered_on}</span>
                  {e.reason || KINDS[e.kind]}
                  {e.reason && e.kind === "set" && <span className="ml-2 text-xs text-mist">set by hand</span>}
                </span>
                <span className="font-mono text-xs">
                  {e.floor_change === e.ceiling_change ? `both ${signed(e.floor_change)}` : `floor ${signed(e.floor_change)}, ceiling ${signed(e.ceiling_change)}`}
                </span>
              </li>
            ))}
          </ul>
          {r.entries.length > 5 && (
            <button type="button" className="mt-1 text-xs text-mist underline hover:text-parchment" onClick={() => setShowAll(!showAll)}>
              {showAll ? "Show fewer" : `Show all ${r.entries.length}`}
            </button>
          )}
        </>
      )}
    </Card>
  );
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
}
