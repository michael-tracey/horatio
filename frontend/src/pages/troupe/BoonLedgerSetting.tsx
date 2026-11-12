import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { BOON_PAGE } from "../../boons";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * Whether the troupe keeps a boon ledger (#685): off by default. On, its running staff
 * keep it on the Boons screen. Switched off, it's hidden everywhere; what was
 * registered is kept, and comes back when it is switched on again.
 */
export function BoonLedgerSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const toast = useToast();
  const on = troupe.boons ?? false;
  const save = useAction(async (next: boolean) => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/boon-ledger", {
        params: { path: { troupe_id: troupe.id } },
        body: { on: next },
      }),
    );
    toast({
      message: next
        ? "The boon ledger is on. Staff keep it on the Boons screen, under Characters."
        : "The boon ledger is off. What was registered is kept, for if you switch it back on.",
    });
  });
  return (
    <Card title="Boons">
      <p className="mb-3 text-sm text-mist">
        Whether Horatio keeps the troupe&apos;s boon ledger: the debts characters owe each other, registered with the Harpy ({BOON_PAGE}). A boon made off the
        record isn&apos;t tracked here, and isn&apos;t enforced.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "The troupe keeps a boon ledger." : "The troupe doesn't keep a boon ledger."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Keep a boon ledger
              <span className="block text-xs text-mist">
                Storytellers and assistant storytellers register boons, and edit, trade, pass on, settle and void them, each with its own log. Switched off,
                it&apos;s hidden everywhere; what was registered is kept, and comes back if it is switched on again.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
