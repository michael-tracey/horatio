import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { ErrorText, Field, Input } from "../../components/ui";
import { makeUp } from "./xpRange";
import { SectionLabel } from "../../components/Headings";
import { SETTINGS } from "./settingsIndex";

const KINDS: Record<string, string> = { game: "Game", downtime: "Downtime", set: "Set by hand" };

/**
 * The troupe's XP floor and ceiling: the least and most a character here could
 * have been given by now. A character built for the troupe starts at the floor.
 * Storytellers can set either by hand, for a chronicle that began before Horatio, saying why.
 * Shown to read wherever `canEdit` is false, as on the Overview.
 */
export function XpRangeCard({ troupeId, canEdit, link }: { troupeId: string; canEdit: boolean; link?: ReactNode }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const range = useQuery({ queryKey: ["xp-range", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/xp-range", path)) });
  // Why is asked each time they are set, and not kept on the form.
  const [reason, setReason] = useState("");
  const form = useSettingForm({ floor: range.data?.floor ?? 0, ceiling: range.data?.ceiling ?? 0 }, async (value) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/xp-range", { ...path, body: { ...value, reason } }));
    setReason("");
  });
  const [showAll, setShowAll] = useState(false);
  if (!range.data) return <ErrorText error={range.error} />;
  const r = range.data;
  const words = makeUp(r);
  const entries = showAll ? r.entries : r.entries.slice(0, 5);

  return (
    <SettingCard
      setting={SETTINGS.xpRange}
      actions={link}
      readOnly={!canEdit}
    >
      {canEdit ? (
        <SettingForm form={form}>
          <div className="flex flex-wrap items-start gap-3">
            <Field label="Floor" hint={words.floor}>
              <Input type="number" min={0} required value={form.value.floor} onChange={(e) => form.set({ floor: Number(e.target.value) })} className="w-24" />
            </Field>
            <Field label="Ceiling" hint={words.ceiling}>
              <Input type="number" min={0} required value={form.value.ceiling} onChange={(e) => form.set({ ceiling: Number(e.target.value) })} className="w-24" />
            </Field>
          </div>
          {form.unsaved && (
            <Field label="Why" hint="For a chronicle that began before Horatio. Games and downtimes still add to them afterwards.">
              <Input required maxLength={500} placeholder="Chronicle began in 2019" value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
          )}
        </SettingForm>
      ) : (
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
      )}
      {r.entries.length > 0 && (
        <>
          <SectionLabel className="mt-4 mb-1">What changed them</SectionLabel>
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
    </SettingCard>
  );
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "0";
}
