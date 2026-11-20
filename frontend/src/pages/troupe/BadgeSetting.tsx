import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { RadioList } from "../../components/RadioList";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { Toggle } from "../../components/Toggle";
import { ErrorText } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

type PrintStatus = "all" | "negative" | "none";

const STATUS: { value: PrintStatus; label: string; meaning: string; text: string }[] = [
  { value: "all", label: "All", meaning: "The status each character carries into a game here, negative status marked out.", text: "all status" },
  {
    value: "negative",
    label: "Negative only",
    meaning: "Negative status must be shown with a sticker, badge or other obvious sign (p. 312).",
    text: "negative status only",
  },
  { value: "none", label: "None", meaning: "The space is left for stickers.", text: "no status" },
];

/** What the troupe's game badges print: the titles held here, how much status, and
 * each character's pronouns (never the player's). */
export function BadgeSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useSaveOnChange((body: { badge_titles?: boolean; badge_status?: PrintStatus; badge_pronouns?: boolean }) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body })),
  );
  const status = STATUS.find((o) => o.value === troupe.badge_status) ?? STATUS[0]!;
  return (
    <SettingCard setting={SETTINGS.badges} readOnly={!canEdit}>
      {!canEdit ? (
        <p className="text-sm">
          Badges print {troupe.badge_titles ? "titles" : "no titles"}, {status.text}
          {troupe.badge_pronouns ? " and character pronouns" : ""}.
        </p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <Toggle label="Print titles" checked={troupe.badge_titles} disabled={save.isPending} onChange={(on) => save.mutate({ badge_titles: on })} />
          <Toggle
            label="Print character pronouns"
            hint="Under the name, where its player gave them. A badge never prints the player's."
            checked={troupe.badge_pronouns}
            disabled={save.isPending}
            onChange={(on) => save.mutate({ badge_pronouns: on })}
          />
          <RadioList
            label="Print status"
            labelClassName="mb-1"
            value={status.value}
            options={STATUS.map((o) => ({ value: o.value, label: o.label, hint: o.meaning }))}
            disabled={save.isPending}
            onChange={(status) => save.mutate({ badge_status: status })}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}
