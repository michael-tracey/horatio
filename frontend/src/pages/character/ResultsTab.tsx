import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, unwrap } from "../../api/client";
import { Badge, Card, Empty, ErrorText, Loading, RichText } from "../../components/ui";
import { markSeen } from "./resultsSeen";

export function ResultsTab({ characterId }: { characterId: string }) {
  const results = useQuery({
    queryKey: ["results", characterId],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/downtime/results", { params: { path: { character_id: characterId } } })),
  });
  // Shown here, so no longer new on the tab's count.
  useEffect(() => {
    const newest = (results.data ?? []).map((r) => r.delivered_at).filter((d) => d !== null)
      .sort((a, b) => Date.parse(a) - Date.parse(b))
      .at(-1);
    if (newest) markSeen(characterId, newest);
  }, [characterId, results.data]);
  if (results.isPending) return <Loading />;
  if (results.error) return <ErrorText error={results.error} />;
  if (!results.data.length) return <Empty>No downtime results have been delivered yet.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      {results.data.map((r) => (
        <Card key={r.cycle_id} title={r.cycle_name} actions={r.updated && <Badge tone="gold">updated</Badge>}>
          <RichText text={r.message} />
        </Card>
      ))}
    </div>
  );
}
