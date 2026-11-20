import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { RetainerRulesOut } from "../../api/types";
import { Checkbox } from "../../components/Checkbox";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { ErrorText, Input, Loading, Select } from "../../components/ui";
import { bodyOf, draftOf, draftProblem, MOST_GROWTH, MOST_UPKEEP, type RulesDraft } from "./retainerRules";
import { SETTINGS } from "./settingsIndex";

/**
 * House rules for Retainers (issue #442), neither in the book and each off unless
 * switched on: upkeep, in Blood or Willpower, a game or a month; and growth, XP a
 * month given as a downtime cycle closes.
 */
export function RetainerRules({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const rules = useQuery({ queryKey: ["retainer-rules", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/retainer-rules", path)) });
  if (rules.isPending) return <Loading />;
  if (rules.error) return <ErrorText error={rules.error} />;
  const now = rules.data;

  return (
    <SettingCard
      setting={SETTINGS.retainerRules}
      readOnly={!canEdit}
    >
      {canEdit ? (
        <RulesForm troupeId={troupeId} rules={now} />
      ) : (
        <dl className="grid gap-1 text-sm sm:grid-cols-[8rem_1fr]">
          <dt className="text-mist">Upkeep</dt>
          <dd>{now.upkeep_text ?? "None."}</dd>
          <dt className="text-mist">Growth</dt>
          <dd>{now.growth_text ?? "None."}</dd>
        </dl>
      )}
    </SettingCard>
  );
}

function RulesForm({ troupeId, rules }: { troupeId: string; rules: RetainerRulesOut }) {
  const form = useSettingForm(draftOf(rules), (value: RulesDraft) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/retainer-rules", { params: { path: { troupe_id: troupeId } }, body: bodyOf(value) })),
  );
  const draft = form.value;
  const upkeep = (patch: Partial<RulesDraft["upkeep"]>) => form.set({ upkeep: { ...draft.upkeep, ...patch } });
  return (
    <SettingForm form={form} problem={draftProblem(draft)}>
      <fieldset className="flex flex-col gap-2">
        <Checkbox label="Retainers cost upkeep" checked={draft.upkeepOn} onChange={(upkeepOn) => form.set({ upkeepOn })} />
        {draft.upkeepOn && (
          <div className="ml-6 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              Each
              <Input type="number" min={1} max={MOST_UPKEEP} required value={draft.upkeep.amount} onChange={(e) => upkeep({ amount: Number(e.target.value) })} className="w-20" />
            </label>
            <label className="flex flex-col gap-1">
              Of
              <Select value={draft.upkeep.pool} onChange={(e) => upkeep({ pool: e.target.value as "blood" | "willpower" })}>
                <option value="blood">Blood</option>
                <option value="willpower">Willpower</option>
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              Taken
              <Select value={draft.upkeep.per} onChange={(e) => upkeep({ per: e.target.value as "game" | "month" })}>
                <option value="game">Each game, as the night starts</option>
                <option value="month">Each month</option>
              </Select>
            </label>
            {draft.upkeep.per === "month" && (
              <label className="flex flex-col gap-1">
                When
                <Select value={draft.upkeep.month_at} onChange={(e) => upkeep({ month_at: e.target.value as "game" | "downtime" })}>
                  <option value="game">At the month&rsquo;s first game</option>
                  <option value="downtime">As a downtime cost, when a cycle closes</option>
                </Select>
              </label>
            )}
            <Checkbox label="Ghoul Retainers only" checked={draft.upkeep.ghouls_only} onChange={(ghouls_only) => upkeep({ ghouls_only })} />
          </div>
        )}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <Checkbox label="Retainers gain XP" checked={draft.growthOn} onChange={(growthOn) => form.set({ growthOn })} />
        {draft.growthOn && (
          <label className="ml-6 flex flex-col gap-1">
            XP a month for each Retainer, given as a downtime cycle closes
            <Input type="number" min={1} max={MOST_GROWTH} required value={draft.growth} onChange={(e) => form.set({ growth: Number(e.target.value) })} className="w-20" />
          </label>
        )}
      </fieldset>
    </SettingForm>
  );
}
