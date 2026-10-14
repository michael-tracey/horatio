import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { LogList } from "../../components/LogList";
import { Card, Empty, ErrorText, Loading } from "../../components/ui";

/** Everything done to the character, newest first. */
export function CharacterLogTab({ characterId }: { characterId: string }) {
  const log = useQuery({
    queryKey: ["character-log", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/log", { params: { path: { character_id: characterId } } })),
  });
  if (log.isPending) return <Loading />;
  if (log.error) return <ErrorText error={log.error} />;
  if (!log.data.length) return <Empty>Nothing has happened yet.</Empty>;

  return (
    <Card title="Log">
      <LogList entries={log.data} />
    </Card>
  );
}
