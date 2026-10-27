import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeLinesVeils } from "../../api/types";
import { AtHandle } from "../../components/PersonPicker";
import { Card, Empty, ErrorText, Loading } from "../../components/ui";

type Gathered = TroupeLinesVeils["lines"][number];

/**
 * Every line and veil the troupe's players have given, on one screen, for its
 * staff to plan games. Whose each one is shows only for players who share theirs
 * with other players; staff open each player's profile for the rest.
 */
export function LinesVeilsTab({ troupeId }: { troupeId: string }) {
  const found = useQuery({
    queryKey: ["lines-veils", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/lines-veils", { params: { path: { troupe_id: troupeId } } })),
  });
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const data = found.data;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        What the troupe’s players don’t want in their games, for staff only. A <strong className="text-parchment">line</strong> won’t happen in
        play around them at all; a <strong className="text-parchment">veil</strong> happens only off-screen. A name shows only where that
        player shares theirs with other players.
      </p>
      {data.players.length === 0 ? (
        <Empty>No player here has given any yet.</Empty>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <GatheredList title="Lines" items={data.lines} none="No lines." />
            <GatheredList title="Veils" items={data.veils} none="No veils." />
          </div>
          <Card title="Players who have given them">
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {data.players.map((p) => (
                <li key={p.id}>
                  <Link to={`/players/${p.id}`} className="hover:text-gold">
                    {p.display_name} <AtHandle handle={p.handle} />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}

function GatheredList({ title, items, none }: { title: string; items: Gathered[]; none: string }) {
  return (
    <Card title={title}>
      {items.length === 0 ? (
        <Empty>{none}</Empty>
      ) : (
        <ul aria-label={title} className="divide-y divide-ash text-sm">
          {items.map((item) => (
            <li key={item.text} className="flex flex-wrap items-baseline gap-x-2 py-1.5">
              <span className="text-parchment">{item.text}</span>
              {item.count > 1 && <span className="text-xs text-mist">×{item.count}</span>}
              {item.shared_by.length > 0 && (
                <span className="text-xs text-mist">
                  {item.shared_by.map((p, i) => (
                    <span key={p.id}>
                      {i > 0 && ", "}
                      <Link to={`/players/${p.id}`} className="hover:text-gold">
                        {p.display_name}
                      </Link>
                    </span>
                  ))}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
