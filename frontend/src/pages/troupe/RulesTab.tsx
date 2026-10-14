import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Card, ErrorText, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";

const STRENGTHS: { value: string; label: string }[] = [
  { value: "refuse", label: "Refuse" },
  { value: "complete", label: "Needed to finish creation" },
  { value: "review", label: "Allow, for our review" },
  { value: "note", label: "Only note it" },
  { value: "off", label: "Off" },
];
const label = (value: string) => STRENGTHS.find((s) => s.value === value)?.label ?? value;

/**
 * The rule set's checks and how this troupe plays them. Storytellers can make a
 * check stricter, looser, reviewed by them, or switch it off.
 */
export function RulesTab({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [query, setQuery] = useState("");
  const checks = useQuery({
    queryKey: ["checks", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/checks", { params: { path: { troupe_id: troupeId } } })),
  });
  const change = useAction((body: { key: string; strength: string | null }) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/checks/{key}", {
        params: { path: { troupe_id: troupeId, key: body.key } },
        body: { strength: body.strength as "off" | null },
      }),
    ),
  );
  if (checks.isPending) return <Loading />;
  if (checks.error) return <ErrorText error={checks.error} />;
  const q = query.trim().toLowerCase();
  const shown = checks.data.filter((c) => !q || `${c.about} ${c.message}`.toLowerCase().includes(q));
  const changed = checks.data.filter((c) => c.house).length;

  return (
    <Card title="Rules">
      <p className="mb-3 text-sm text-mist">
        What sheets may hold, from the rule set. {changed ? `${changed} played differently here.` : "All played as written."}
      </p>
      <Input aria-label="Search rules" placeholder={`Search ${checks.data.length} rules…`} value={query} onChange={(e) => setQuery(e.target.value)} className="mb-3" />
      <ul className="divide-y divide-ash">
        {shown.map((c) => (
          <li key={c.key} className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
            <span className="min-w-0 text-sm">
              <span className="text-parchment">{c.message || c.about}</span>
              {c.page && <span className="text-mist"> (p. {c.page})</span>}
            </span>
            {canEdit ? (
              <Select
                aria-label={`How we play: ${c.message || c.about}`}
                value={c.house ?? ""}
                onChange={(e) => change.mutate({ key: c.key, strength: e.target.value || null })}
                className={`w-auto shrink-0 ${c.house ? "text-gold" : ""}`}
              >
                <option value="">As written: {label(c.strength)}</option>
                {STRENGTHS.filter((s) => s.value !== c.strength).map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            ) : (
              <span className={`text-xs ${c.house ? "text-gold" : "text-mist"}`}>{label(c.house ?? c.strength)}</span>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={change.error} />
    </Card>
  );
}
