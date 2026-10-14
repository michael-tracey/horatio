import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Card, Empty, ErrorText, Loading } from "../../components/ui";

/** What has happened in the troupe, newest first, for its storytellers and assistants. */
export function LogTab({ troupeId }: { troupeId: string }) {
  const log = useQuery({
    queryKey: ["log", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/log", { params: { path: { troupe_id: troupeId } } })),
    refetchInterval: 60_000,
  });
  if (log.isPending) return <Loading />;
  if (log.error) return <ErrorText error={log.error} />;
  if (!log.data.length) return <Empty>Nothing has happened yet.</Empty>;

  let lastDay = "";
  return (
    <Card title="Log">
      <ol className="text-sm">
        {log.data.map((entry) => {
          const at = new Date(entry.at);
          const day = at.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
          const heading = day !== lastDay ? day : null;
          lastDay = day;
          return (
            <li key={entry.id}>
              {heading && <h3 className="mt-4 mb-1 font-sans text-xs tracking-wide text-mist uppercase first:mt-0">{heading}</h3>}
              <div className="flex gap-3 border-b border-ash/50 py-1.5">
                <time className="w-14 shrink-0 text-mist" dateTime={entry.at}>
                  {at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                </time>
                <span>
                  {entry.character_id ? (
                    <Link className="hover:text-gold" to={`/characters/${entry.character_id}?troupe=${troupeId}`}>
                      {entry.message}
                    </Link>
                  ) : (
                    entry.message
                  )}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
