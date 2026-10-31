import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** House option: the troupe's sect recognises the pursuit of Golconda, so Golconda Seekers hold the innate status Enlightened (Vol. 2, p. 267). Off unless switched on. */
export function GolcondaSetting({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const save = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/golconda", { ...path, body: { on } })));
  if (!troupe.data) return null;
  const on = troupe.data.golconda_enlightened;
  return (
    <Card title="Golconda and Enlightened">
      <p className="mb-3 text-sm text-mist">
        A character with the Path of Enlightenment merit of a path its sect Accepts holds the innate status Enlightened (Vol. 2, pp. 266-267). As an optional rule, a sect can
        recognise the pursuit of Golconda too.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "Golconda Seekers are Enlightened here." : "Golconda Seekers are not Enlightened here."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Golconda Seekers are Enlightened
              <span className="block text-xs text-mist">A character with Golconda Seeker holds the innate status Enlightened (Vol. 2, p. 267).</span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
