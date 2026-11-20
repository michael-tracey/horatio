import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { Toggle } from "../../components/Toggle";
import { ErrorText } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

/** What the troupe's Who's Who shows of sect status: none, or the negative status
 * each character carries into a game here, which is public in the sect anyway. */
export function WhosWhoSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useSaveOnChange((body: { whos_who_negative?: boolean; sire_lines_players?: boolean }) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body })),
  );
  return (
    <SettingCard
      setting={SETTINGS.whosWho}
      readOnly={!canEdit}
    >
      {!canEdit ? (
        <div className="flex flex-col gap-1 text-sm">
          <p>The Who’s Who shows {troupe.whos_who_negative ? "negative status" : "no sect status"}.</p>
          <p>Its sire lines are for {troupe.sire_lines_players ? "its players and staff" : "its staff only"}.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <Toggle
            label="Show negative status"
            hint="The negative status each character carries into a game here, which is public in the sect (p. 312)."
            checked={troupe.whos_who_negative}
            disabled={save.isPending}
            onChange={(on) => save.mutate({ whos_who_negative: on })}
          />
          <Toggle
            label="Show the sire lines to players"
            hint="Who sired whom, among the characters on the Who’s Who. A sire its player keeps secret, or one not on the Who’s Who, is left out. Staff always see every line."
            checked={troupe.sire_lines_players}
            disabled={save.isPending}
            onChange={(on) => save.mutate({ sire_lines_players: on })}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}
