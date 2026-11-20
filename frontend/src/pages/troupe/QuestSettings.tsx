import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { ErrorText, Field, Input, Loading } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

/**
 * How many quests a character may ask for each cycle, in the Quests tab's Settings (#785, #909).
 * Quests are switched on and off in the Features list, on Troupe settings (#784), the one place.
 */
export function QuestSettings({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const form = useSettingForm({ perCycle: troupe.data?.quest_requests_per_cycle ?? 0 }, ({ perCycle }) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/quest-settings", { ...path, body: { enabled: troupe.data?.quests_enabled ?? false, requests_per_cycle: perCycle } })),
  );
  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const now = troupe.data.quest_requests_per_cycle;
  const requests = (n: number) => (n === 1 ? "1 request" : `${n} requests`);

  return (
    <SettingCard
      setting={SETTINGS.questRequests}
      readOnly={!canEdit}
    >
      {canEdit ? (
        <SettingForm form={form}>
          <Field label="Requests per character per cycle">
            <Input type="number" min={0} max={20} required value={form.value.perCycle} onChange={(e) => form.set({ perCycle: Number(e.target.value) })} className="w-24" />
          </Field>
        </SettingForm>
      ) : (
        <p className="text-sm">{`${requests(now)} per character each downtime cycle.`}</p>
      )}
    </SettingCard>
  );
}
