import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * How many quests a character may ask for each cycle, folded at the top of the Quests tab (#785).
 * Quests are switched on and off in the Features list, on Troupe settings (#784), the one place.
 */
export function QuestSettings({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [draft, setDraft] = useState<number | null>(null);
  const save = useAction(async ({ enabled, perCycle }: { enabled: boolean; perCycle: number }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/quest-settings", { ...path, body: { enabled, requests_per_cycle: perCycle } }));
    setDraft(null);
  });
  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const t = troupe.data;
  const now = t.quest_requests_per_cycle;
  const requests = (n: number) => (n === 1 ? "1 request" : `${n} requests`);

  return (
    <Card
      title="Quest requests"
      actions={
        canEdit &&
        draft === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change quest settings" onClick={() => setDraft(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Quests (MET: VTM Vol. II Issue 1, pp. 99-110): players ask for them, staff build them with requirements and scenarios, and Horatio keeps track as the
        party meets them. A request staff answer as not needed, or one withdrawn, does not count. Quests are switched on and off in the Features list, on Troupe
        settings.
      </p>
      {draft === null ? (
        <p className="text-sm">{`${requests(now)} per character each downtime cycle.`}</p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({ enabled: t.quests_enabled, perCycle: draft });
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            Requests per character per cycle
            <Input type="number" min={0} max={20} required value={draft} onChange={(e) => setDraft(Number(e.target.value))} className="w-24" />
          </label>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      )}
    </Card>
  );
}
