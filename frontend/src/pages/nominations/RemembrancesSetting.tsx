import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** "Remembrances" (#471): memories of a character who leaves play, asked for in the next downtime. Off unless switched on; independent of Player Nominations. */
export function RemembrancesSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/remembrances", { params: { path: { troupe_id: troupe.id } }, body: { on } })));
  const on = troupe.remembrances ?? false;
  return (
    <Card title="Remembrances">
      <p className="mb-3 text-sm text-mist">
        When a character leaves play, storytellers can open remembrances for them. The next downtime asks everyone for a memory of them; storytellers read them, then
        publish them with the month’s Player Nominations, without names. They’re kept with the character, and on the Who’s Who.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "The troupe uses Remembrances." : "The troupe doesn't use Remembrances."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Remembrances
              <span className="block text-xs text-mist">
                Retiring a character offers to open them, and each cycle that asks for some has a Remembrances section on the downtime form. Switched off, none can be
                opened or written, and nothing of them shows, except those already published: they stay on the characters and the Who’s Who, as they belong to the
                people remembered.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
