import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** "Player Nominations" (#470): players praise each other's roleplaying in their downtimes, published monthly without names. Off unless switched on. */
export function NominationsSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/player-nominations", { params: { path: { troupe_id: troupe.id } }, body: { on } })));
  const on = troupe.player_nominations ?? false;
  return (
    <Card title="Player Nominations">
      <p className="mb-3 text-sm text-mist">
        In each downtime, players write short notes praising others’ roleplaying. Storytellers read them, take out any that aren’t kind and star the best, then publish them
        each month to the troupe’s players, shuffled and without names. Starred ones rotate at the foot of the troupe’s pages.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "The troupe uses Player Nominations." : "The troupe doesn't use Player Nominations."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Player Nominations
              <span className="block text-xs text-mist">
                Each downtime form gets a Player Nominations section, and each cycle a Nominations tab. Switched off, none of it shows anywhere, and what was written and
                published is kept for when it’s on again.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
