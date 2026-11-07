import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { changedText } from "../../backgroundChanges";
import { Card } from "../../components/ui";
import { useDates } from "../../dates";

/** Backgrounds raised or lowered for now, from a downtime: Crafts, Performance, overtaxed Resources. Shown only while there are any. */
export function BackgroundChanges({ characterId }: { characterId: string }) {
  const dates = useDates();
  const changes = useQuery({
    queryKey: ["background-changes", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/background-changes", { params: { path: { character_id: characterId } } })),
  });
  if (!changes.data?.length) return null;
  return (
    <Card dense title="Backgrounds changed for now">
      <ul className="flex flex-col gap-1 text-sm">
        {changes.data.map((b) => (
          <li key={b.trait}>{changedText(b, dates)}</li>
        ))}
      </ul>
    </Card>
  );
}
