import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** Whether the troupe's players see the court over time (#712): who held each title,
 * and when. Titles are public at court; how each holding ended, and status, stay staff's. */
export function CourtHistorySetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((court_history_players: boolean) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { court_history_players } })),
  );
  const on = troupe.court_history_players ?? false;
  return (
    <Card title="The court over time">
      {!canEdit ? (
        <p className="text-sm">{on ? "Players and staff see who held each title, and when." : "Only staff see who held each title, and when."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-mist">Staff always see it under Characters › Court, with status over time.</p>
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Players see it too
              <span className="block text-xs text-mist">Who held each title, and when: titles are public at court. Not how each one ended, nor anyone’s status.</span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
