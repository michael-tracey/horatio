import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { BOND_PAGE, BOND_SETTINGS, type BondSetting } from "../../bonds";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * How far Horatio tracks the troupe's blood bonds: not at all (the default); with its
 * running staff recording them; with players reporting drinks for staff to approve;
 * or with players recording them (#661). Switching it off hides every bond and every
 * drink waiting; what was recorded is kept.
 */
export function BloodBondsSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const toast = useToast();
  const now = troupe.blood_bonds ?? "off";
  const save = useAction(async (setting: NonNullable<BondSetting>) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/blood-bonds", { params: { path: { troupe_id: troupe.id } }, body: { setting } }));
    toast({
      message:
        setting === "off"
          ? "Blood bonds aren't tracked now. What was recorded is kept, for if you switch them back on."
          : setting === "staff"
            ? "Blood bonds are tracked. Staff keep them on the Bonds screen, under Court."
            : "Blood bonds are tracked. Players report drinks on their sheets and in the Play View; staff see every bond on the Bonds screen, under Court.",
    });
  });
  const chosen = BOND_SETTINGS.find((s) => s.value === now) ?? BOND_SETTINGS[0]!;
  return (
    <Card title="Blood bonds">
      <p className="mb-3 text-sm text-mist">
        Whether Horatio keeps the blood bonds between characters ({BOND_PAGE}). A thrall&apos;s player sees their own bonds, a regnant&apos;s player only those
        staff mark known to them, and nobody else any. Changing the mode leaves drinks already waiting where they are.
        Switched off, they&apos;re hidden everywhere; whatever was recorded is kept, and comes back if it is switched on again.
      </p>
      {!canEdit ? (
        <p className="text-sm">
          {chosen.label}. <span className="text-mist">{chosen.meaning}</span>
        </p>
      ) : (
        <fieldset className="flex flex-col gap-2 text-sm" disabled={save.isPending}>
          <legend className="sr-only">How Horatio tracks blood bonds</legend>
          {BOND_SETTINGS.map((s) => (
            <label key={s.value} className="flex items-start gap-2">
              <input type="radio" name="blood-bonds" className="mt-1" checked={now === s.value} onChange={() => save.mutate(s.value)} />
              <span>
                {s.label}
                {s.value === "off" && <span className="text-mist"> (the default)</span>}
                <span className="block text-xs text-mist">{s.meaning}</span>
              </span>
            </label>
          ))}
          <ErrorText error={save.error} />
        </fieldset>
      )}
    </Card>
  );
}
