import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** Optional rule: a dot of a rare discipline, learned from a teacher, takes two downtime actions (MET: VtM core p. 113). Off unless switched on. */
export function RareDisciplinesSetting({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const save = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/rare-disciplines", { ...path, body: { on } })));
  if (!troupe.data) return null;
  const on = troupe.data.rare_disciplines_two_actions;
  return (
    <Card title="Rare disciplines">
      <p className="mb-3 text-sm text-mist">
        Learning a discipline dot takes a downtime action. As an optional rule, a rare discipline is harder to teach and learn (MET: VtM core p. 113). Every discipline but
        Animalism, Auspex, Celerity, Dominate, Fortitude, Obfuscate, Potence and Presence is rare (p. 111).
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "A dot of a rare discipline takes two downtime actions here." : "A dot of a rare discipline takes one downtime action here, as any other."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Rare disciplines take two downtime actions a dot
              <span className="block text-xs text-mist">For one learned from a teacher, out of clan. Dots already learned keep what they cost.</span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
