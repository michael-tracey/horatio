import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/** What a new character built for the troupe starts with, in words. */
export function startingText(t: Pick<TroupeOut, "new_character_incentive" | "new_character_xp" | "starting_xp" | "xp_floor">): string {
  if (!t.new_character_incentive) return `${t.new_character_xp} XP, the troupe's XP floor`;
  return `${t.new_character_xp} XP: the starting ${t.starting_xp} XP and the New Character Incentive`;
}

/**
 * The optional New Character Incentive (MET: VTM p. 349): a new character built for the
 * troupe starts with its starting XP and a quarter of the XP a character could have
 * earned here (the XP ceiling less the starting XP), rather than at the XP floor.
 * Characters already made keep their XP.
 */
export function NewCharacterIncentive({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const save = useAction((on: boolean) => unwrap(api.PATCH("/api/troupes/{troupe_id}", { ...path, body: { new_character_incentive: on } })));
  if (!troupe.data) return null;
  const t = troupe.data;
  const earned = Math.max(0, t.xp_ceiling - t.starting_xp);
  return (
    <Card title="New Character Incentive">
      <p className="mb-3 text-sm text-mist">
        Without it, a new character built here starts at the XP floor. With it, as the book's optional rule has it (p. 349), a new character starts with the starting XP and
        a quarter of the XP a character could have earned here: {t.starting_xp} XP and a quarter of {earned}, {t.starting_xp + Math.floor(earned / 4)} XP now. Characters
        already made keep their XP.
      </p>
      {!canEdit ? (
        <p className="text-sm">New characters start with {startingText(t)}.</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={t.new_character_incentive} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Use the New Character Incentive
              <span className="block text-xs text-mist">New characters start with {startingText({ ...t, new_character_incentive: true, new_character_xp: t.starting_xp + Math.floor(earned / 4) })}.</span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
