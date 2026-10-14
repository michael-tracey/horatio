import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card, Empty, ErrorText, Loading, RichText } from "../../components/ui";

export function ResultsTab({ characterId }: { characterId: string }) {
  const results = useQuery({
    queryKey: ["results", characterId],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/downtime/results", { params: { path: { character_id: characterId } } })),
  });
  if (results.isPending) return <Loading />;
  if (results.error) return <ErrorText error={results.error} />;
  if (!results.data.length) return <Empty>No downtime results have been delivered yet.</Empty>;
  return (
    <div className="flex flex-col gap-4">
      {results.data.map((r) => (
        <Card key={r.cycle_id} title={r.cycle_name}>
          <RichText text={r.message} />
        </Card>
      ))}
    </div>
  );
}
