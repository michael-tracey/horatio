import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { RadioList } from "../../components/RadioList";
import { Toggle } from "../../components/Toggle";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText } from "../../components/ui";
import { SETTINGS, type CardSetting } from "./settingsIndex";

type Setting = "players" | "staff";

const OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "players",
    label: "Players keep their own",
    meaning:
      "A player adds and removes fleeting and negative status on their own character, naming who gave it. Only the one who gave a negative status, or staff, take it off early.",
  },
  {
    value: "staff",
    label: "Staff only",
    meaning: "Only storytellers and assistant storytellers add or remove status. Players still spend it at games.",
  },
];

const TITLE_OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "players",
    label: "Players choose their own",
    meaning:
      "A player chooses their character's titles from the troupe's titles of its sect, and the storytellers and assistant storytellers are told. A title only one character holds at a time is staff's to give while someone holds it.",
  },
  {
    value: "staff",
    label: "Staff only",
    meaning: "Only storytellers and assistant storytellers give and take titles, by appointment. Players still choose which of their titles is active.",
  },
];

/** Status on sheets: who adds and removes fleeting and negative status on the troupe's characters. */
export function StatusSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  return (
    <WhoSetting
      troupe={troupe}
      canEdit={canEdit}
      field="status_by"
      setting={SETTINGS.statusOnSheets}
      options={OPTIONS}
    />
  );
}

/** Titles on sheets: whether players choose their characters' titles, or only staff give them. */
export function TitlesSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  return (
    <WhoSetting
      troupe={troupe}
      canEdit={canEdit}
      field="titles_by"
      setting={SETTINGS.titlesOnSheets}
      options={TITLE_OPTIONS}
    />
  );
}

/**
 * House rule (issue #441): each character's one source of abiding status is chosen as
 * it checks in to a game, before it enters play, and fixed for the game. Off: chosen on
 * the Play View as the game begins, as the book has it.
 */
export function StatusAtCheckinSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useSaveOnChange((on: boolean) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { status_at_checkin: on } })),
  );
  const on = troupe.status_at_checkin;
  return (
    <SettingCard
      setting={SETTINGS.nightsStatus}
      readOnly={!canEdit}
    >
      {!canEdit ? (
        <p className="text-sm">{on ? "Chosen at check-in, and fixed for the game." : "Chosen on the Play View as the game begins."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <Toggle
            label="Choose the night's status at check-in"
            hint="Players choose the source as they check in, and can't change it on the Play View. Storytellers and assistant storytellers can, with a reason for the game's log. Status given for a single night is held beside it."
            checked={on}
            disabled={save.isPending}
            onChange={(next) => save.mutate(next)}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}

/** A setting of who does something on the troupe's sheets: its players, or staff only. Saved as it is chosen. */
function WhoSetting({
  troupe,
  canEdit,
  field,
  setting,
  options,
}: {
  troupe: TroupeOut;
  canEdit: boolean;
  field: "status_by" | "titles_by";
  setting: CardSetting;
  options: { value: Setting; label: string; meaning: string }[];
}) {
  const save = useSaveOnChange((value: Setting) => unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { [field]: value } })));
  const now = troupe[field] as Setting;
  const current = options.find((o) => o.value === now) ?? options[0]!;
  return (
    <SettingCard setting={setting} readOnly={!canEdit}>
      {!canEdit ? (
        <p className="text-sm">
          {current.label}. <span className="text-mist">{current.meaning}</span>
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <RadioList
            label={setting.title}
            hideLabel
            value={now}
            options={options.map((o) => ({ value: o.value, label: o.label, hint: o.meaning }))}
            disabled={save.isPending}
            onChange={(value) => save.mutate(value)}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}
