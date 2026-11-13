import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BuildEntry } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { useClanName } from "../../components/ClanNames";
import { Badge, Card, Empty, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";

/** The characters built to this troupe's rules whose players haven't yet asked to make
 * it home (#774): who is coming, who may be stuck, and what won't pass as it stands. */
export function BeingBuiltTab({ troupeId }: { troupeId: string }) {
  const builds = useQuery({
    queryKey: ["builds", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/builds", { params: { path: { troupe_id: troupeId } } })),
  });

  return (
    <>
      <p className="mb-4 text-sm text-mist">
        Characters built to this troupe&apos;s rules whose players haven&apos;t asked to make it home yet. Once they ask, they move to Approvals.
      </p>
      {builds.isPending ? (
        <Loading />
      ) : builds.data?.length ? (
        <div className="flex flex-col gap-4">
          {builds.data.map((b) => (
            <BuildCard key={b.character_id} troupeId={troupeId} build={b} />
          ))}
        </div>
      ) : (
        <Empty>No one is building a character to this troupe&apos;s rules.</Empty>
      )}
      <ErrorText error={builds.error} />
    </>
  );
}

function BuildCard({ troupeId, build: b }: { troupeId: string; build: BuildEntry }) {
  const named = useClanName();
  const dates = useDates();
  const what = [b.clan && named(b.clan), b.sect].filter(Boolean).join(", ");

  return (
    <Card
      title={
        <Link to={`/print/troupes/${troupeId}/builds/${b.character_id}`} className="inline-flex items-center gap-2 hover:underline">
          <Avatar name={b.character_name} picture={b.picture} clan={b.clan} size="xs" />
          {b.character_name}
        </Link>
      }
      actions={<Badge tone={b.creation_complete ? "gold" : "mist"}>{b.creation_complete ? "Finished, not yet submitted" : "In creation"}</Badge>}
    >
      <p className="text-sm text-parchment">
        {b.player_name} <span className="text-mist">@{b.player_handle}</span>
        {what && <span className="text-mist"> · {what}</span>}
      </p>
      {!b.creation_complete && (
        <p className="mt-1 text-sm text-mist">{b.to_place.length ? `Still to place: ${b.to_place.join(", ")}.` : "Every pick placed."}</p>
      )}
      {b.broken.length > 0 && (
        <div className="mt-2">
          <p className="text-sm text-blood">
            {b.broken.length === 1 ? "1 rule" : `${b.broken.length} rules`} it would be refused on at Finish creation:
          </p>
          <ul className="ml-5 list-disc text-sm text-mist">
            {b.broken.map((m) => (
              <li key={m}>{named(m)}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-xs text-mist">
        Last changed {dates.dateTime(b.changed_at)} · started {dates.date(b.started_at)} ·{" "}
        <Link to={`/print/troupes/${troupeId}/builds/${b.character_id}`} className="underline hover:text-parchment">
          Read the sheet
        </Link>
      </p>
    </Card>
  );
}
