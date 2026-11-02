import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { DefaultBloodlinesOut } from "../../api/types";
import { Button, Card, ErrorText, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";

type Row = DefaultBloodlinesOut["clans"][number];

/** A clan's default in words: the bloodline, or the plain clan. */
export function defaultText(clan: string, line: string | null | undefined): string {
  return line && line !== clan ? line : `The plain ${clan}, no bloodline`;
}

/** The book's default for a clan, in the troupe's setting or in each sect's. */
export function bookDefault(row: Row, setting: string | null): string {
  if (setting) return defaultText(row.clan, row.book[setting]);
  const sects = Object.entries(row.book);
  if (!sects.length) return defaultText(row.clan, null);
  return sects.map(([sect, line]) => `${line} (${sect})`).join(", ");
}

/**
 * House rule: the bloodline each clan plays as by default (#435). The book names one
 * for some clans in each sect's setting (MET: VTM p. 238): it needs no bloodline
 * merit, and the clan's own line is then a step rarer. A troupe can name another
 * bloodline, or the plain clan, for each clan.
 */
export function DefaultBloodlines({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const defaults = useQuery({
    queryKey: ["default-bloodlines", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/default-bloodlines", path)),
  });
  const save = useAction((chosen: Record<string, string>) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/default-bloodlines", { ...path, body: { defaults: chosen } })),
  );
  if (defaults.isPending) return <Loading />;
  if (defaults.error) return <ErrorText error={defaults.error} />;
  return <DefaultBloodlinesCard data={defaults.data} canEdit={canEdit} save={save.mutateAsync} />;
}

/** The card itself, given what the troupe plays now and how to save a change. */
export function DefaultBloodlinesCard({
  data,
  canEdit,
  save,
}: {
  data: DefaultBloodlinesOut;
  canEdit: boolean;
  save: (defaults: Record<string, string>) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const { clans, setting } = data;
  const own = Object.fromEntries(clans.filter((c) => c.house).map((c) => [c.clan, c.house!]));
  const submit = async (chosen: Record<string, string>) => {
    setSaving(true);
    setError(null);
    try {
      await save(chosen);
      setEditing(null);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };
  return (
    <Card
      title="Default bloodlines"
      actions={
        canEdit &&
        editing === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change default bloodlines" onClick={() => setEditing(own)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        The bloodline a clan plays as by default. It needs no bloodline merit, and the clan's own line is a step rarer instead (MET: VTM p. 238).{" "}
        {setting ? `Unless you say otherwise, it is the book's for the ${setting} setting.` : "Unless you say otherwise, it is the book's for each character's sect."}{" "}
        Finished characters keep the bloodline and merits they have.
      </p>
      {editing === null ? (
        <ul className="flex flex-col divide-y divide-ash text-sm">
          {clans.map((c) => (
            <li key={c.clan} className="flex flex-wrap justify-between gap-x-3 py-1">
              <span>{c.clan}</span>
              <span className={c.house ? "text-parchment" : "text-mist"}>{c.house ? `${defaultText(c.clan, c.house)} (house rule)` : bookDefault(c, setting)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(editing);
          }}
        >
          <ul className="flex flex-col divide-y divide-ash text-sm">
            {clans.map((c) => (
              <li key={c.clan} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1">
                <span>{c.clan}</span>
                <Select
                  aria-label={`${c.clan} default bloodline`}
                  className="h-9 w-auto max-w-full py-0"
                  value={editing[c.clan] ?? ""}
                  onChange={(e) => {
                    const next = { ...editing };
                    if (e.target.value) next[c.clan] = e.target.value;
                    else delete next[c.clan];
                    setEditing(next);
                  }}
                >
                  <option value="">By the book: {bookDefault(c, setting)}</option>
                  <option value={c.clan}>The plain {c.clan}, no bloodline</option>
                  {c.bloodlines.map((line) => (
                    <option key={line} value={line}>
                      {line}
                    </option>
                  ))}
                </Select>
              </li>
            ))}
          </ul>
          <ErrorText error={error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={saving}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
