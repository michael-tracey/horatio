import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { Field, Input } from "../../components/ui";
import { useMe } from "../../hooks";
import { abilities } from "./roles";
import { SETTINGS } from "./settingsIndex";

/** The most an abbreviation may be, as the server has it (horatio.troupe_abbreviations). */
export const LONGEST_ABBREVIATION = 10;

/** Why the server would refuse this abbreviation, or null: letters, digits, "-", "_" and "." only, no spaces. Empty clears it. */
export function abbreviationProblem(value: string): string | null {
  const given = value.trim();
  if (!given) return null;
  return given.length <= LONGEST_ABBREVIATION && /^[\p{L}\p{N}_.-]+$/u.test(given)
    ? null
    : `Up to ${LONGEST_ABBREVIATION} letters, digits, hyphens, underscores or full stops, with no spaces.`;
}

/** What the troupe goes by with none set, in a line. */
export function abbreviationDefaultText(troupe: Pick<TroupeOut, "name" | "abbreviation_default">): string {
  return troupe.abbreviation_default === troupe.name
    ? "Left empty, it goes by its full name, as another troupe goes by its initials."
    : `Left empty, it goes by ${troupe.abbreviation_default}, from the initials of its name.`;
}

/**
 * The troupe's abbreviation (#1153), beside its name, first of Settings › Names: the short
 * name it goes by where its full name won't fit, such as the pill on another troupe's
 * search hit. Whoever may rename the troupe sets it (its lead, and the custodian); its other
 * running staff read it. Unique on the site; empty goes by the one made from its name.
 */
export function AbbreviationSetting({ troupe }: { troupe: TroupeOut }) {
  const me = useMe();
  const canEdit = abilities(troupe.my_role, me.data?.is_custodian ?? false).lead && !troupe.archived;
  const form = useSettingForm({ abbreviation: troupe.abbreviation_set ?? "" }, ({ abbreviation }) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { abbreviation: abbreviation.trim() } })),
  );
  const name = (
    <p className="text-sm">
      <span className="text-mist">Name:</span> {troupe.name}
    </p>
  );
  if (!canEdit)
    return (
      <SettingCard setting={SETTINGS.abbreviation} readOnly="The troupe's lead storyteller changes this.">
        <div className="flex flex-col gap-1">
          {name}
          <p className="text-sm">
            <span className="text-mist">Goes by:</span> {troupe.abbreviation}
            {!troupe.abbreviation_set && <span className="text-mist"> (none set)</span>}
          </p>
        </div>
      </SettingCard>
    );
  return (
    <SettingCard setting={SETTINGS.abbreviation}>
      <SettingForm form={form} problem={abbreviationProblem(form.value.abbreviation)}>
        {name}
        <Field label="Abbreviation" hint={abbreviationDefaultText(troupe)}>
          <Input
            value={form.value.abbreviation}
            onChange={(e) => form.set({ abbreviation: e.target.value })}
            placeholder={troupe.abbreviation_default === troupe.name ? undefined : troupe.abbreviation_default}
            maxLength={LONGEST_ABBREVIATION}
            autoComplete="off"
            spellCheck={false}
            className="w-40"
          />
        </Field>
      </SettingForm>
    </SettingCard>
  );
}
