import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** "Items can expire" (#443): staff give items an expiry, on a day, after a number of games, or with a downtime cycle. Off unless switched on. */
export function ItemExpirySetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/item-expiry", { params: { path: { troupe_id: troupe.id } }, body: { on } })));
  const on = troupe.items_expire ?? false;
  return (
    <Card title="Items that expire">
      <p className="mb-3 text-sm text-mist">Items found on a plot can have an expiry date. Once it comes, the item is taken back and its history kept.</p>
      {!canEdit ? (
        <p className="text-sm">{on ? "Staff can give items that expire." : "Items don't expire here."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Items can expire
              <span className="block text-xs text-mist">
                Staff giving or changing an item can set it to expire on a day, after a number of games, or at the end of the downtime cycle. Its holder is warned a week or a game before.
                Switched off, expiries are hidden and wait until it's on again.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
