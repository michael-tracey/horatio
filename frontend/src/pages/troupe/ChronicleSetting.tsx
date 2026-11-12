import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** Whether the troupe's players see the chronicle (#711): its public history only,
 * what the troupe already shows them. Embraces, diablerie and status stay staff's. */
export function ChronicleSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((chronicle_players: boolean) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { chronicle_players } })),
  );
  const on = troupe.chronicle_players ?? false;
  return (
    <Card title="The chronicle">
      {!canEdit ? (
        <p className="text-sm">{on ? "Players and staff see the troupe’s chronicle." : "Only staff see the troupe’s chronicle."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-mist">Staff always see all of it under Characters › Chronicle: Embraces, deaths, diablerie, status and titles.</p>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Players see it too
              <span className="block text-xs text-mist">
                Only what the troupe already shows them: titles, characters on the Who’s Who joining, and those listed under No longer with us. Not Embraces, diablerie or status.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
