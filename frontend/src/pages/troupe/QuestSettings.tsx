import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** House rule: whether the troupe runs quests, and how many requests a character may make a cycle. */
export function QuestSettings({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [draft, setDraft] = useState<{ enabled: boolean; perCycle: number } | null>(null);
  const save = useAction(async (value: { enabled: boolean; perCycle: number }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/quest-settings", { ...path, body: { enabled: value.enabled, requests_per_cycle: value.perCycle } }));
    setDraft(null);
  });
  if (troupe.isPending) return <Loading />;
  if (troupe.error) return <ErrorText error={troupe.error} />;
  const t = troupe.data;
  const now = { enabled: t.quests_enabled, perCycle: t.quest_requests_per_cycle };
  const shown = draft ?? now;
  const requests = (n: number) => (n === 1 ? "1 request" : `${n} requests`);

  return (
    <Card
      title="Quests"
      actions={
        canEdit &&
        draft === null && (
          <Button variant="ghost" className="min-h-8 px-2" aria-label="Change quest settings" onClick={() => setDraft(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Quests (MET: VTM Vol. II Issue 1, pp. 99-110): players ask for them, staff build them with requirements and scenarios, and Horatio keeps track as the
        party meets them. While quests are off, players see nothing of them. A request staff answer as not needed, or one withdrawn, does not count.
      </p>
      {draft === null ? (
        <p className="text-sm">{now.enabled ? `On: ${requests(now.perCycle)} per character each downtime cycle.` : "Off."}</p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(shown);
          }}
        >
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input type="checkbox" checked={shown.enabled} onChange={(e) => setDraft({ ...shown, enabled: e.target.checked })} />
            Run quests in this troupe
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Requests per character per cycle
            <Input type="number" min={0} max={20} required value={shown.perCycle} onChange={(e) => setDraft({ ...shown, perCycle: Number(e.target.value) })} className="w-24" />
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
