import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Input } from "../../components/ui";
import { useAction } from "../../hooks";

/** House rule: how far back Gossip and Insider Trading and Word on the Street look in the influence log. */
export function InfluenceLookback({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [days, setDays] = useState<number | null>(null);
  const save = useAction(async (value: number) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/influence-lookback", { ...path, body: { days: value } }));
    setDays(null);
  });
  if (!troupe.data) return null;
  const now = troupe.data.influence_lookback_days;
  return (
    <Card
      title="Influence lookups"
      actions={
        canEdit &&
        days === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change how far lookups look back" onClick={() => setDays(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        How far back Gossip and Insider Trading and Word on the Street look in the influence log, counted to the minute from when their cycle closes. The rules say
        three months.
      </p>
      {days === null ? (
        <p className="text-sm">{now === 1 ? "1 day" : `${now} days`}</p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(days);
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            Days to look back
            <Input type="number" min={1} max={3650} required value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-24" />
          </label>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDays(null)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      )}
    </Card>
  );
}
