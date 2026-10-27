import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** What the troupe's Who's Who shows of sect status: none, or the negative status
 * each character carries into a game here, which is public in the sect anyway. */
export function WhosWhoSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((whos_who_negative: boolean) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { whos_who_negative } })),
  );
  return (
    <Card title="Who's Who">
      {!canEdit ? (
        <p className="text-sm">The Who’s Who shows {troupe.whos_who_negative ? "negative status" : "no sect status"}.</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-mist">The troupe’s players and staff see its characters there. It shows no sect status unless you add negative status.</p>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-1"
              checked={troupe.whos_who_negative}
              disabled={save.isPending}
              onChange={(e) => save.mutate(e.target.checked)}
            />
            <span>
              Show negative status
              <span className="block text-xs text-mist">The negative status each character carries into a game here, which is public in the sect (p. 312).</span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
