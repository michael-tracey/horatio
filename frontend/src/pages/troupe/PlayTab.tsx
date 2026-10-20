import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Loading, Notice } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * The troupe at a game: each character's blood, Willpower and health as their
 * Play View has them, a way into each one (and its log), and one reset for
 * everyone after the game.
 */
export function PlayTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const list = useQuery({
    queryKey: ["troupe-play", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/play", path)),
    refetchInterval: 30_000,
  });
  const [asking, setAsking] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const reset = useAction(async () => {
    const result = await unwrap(api.POST("/api/troupes/{troupe_id}/play/reset", path));
    setDone(result.reset);
    setAsking(false);
  });

  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  return (
    <div className="flex flex-col gap-6">
      <Card title="At game">
        <p className="mb-3 text-sm text-mist">
          What each character has spent this game, from their Play View. Open one to tap for them, run an NPC, or read what they spent and why.
        </p>
        {list.data.length === 0 ? (
          <Empty>No characters in the troupe yet.</Empty>
        ) : (
          <ul className="divide-y divide-ash">
            {list.data.map((c) => (
              <li key={c.character_id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2.5">
                <span className="min-w-40 flex-1">
                  <Link to={`/play/characters/${c.character_id}`} className="text-parchment underline-offset-2 hover:underline">
                    {c.character_name}
                  </Link>{" "}
                  <span className="text-xs text-mist">
                    {c.player_name}
                    {c.game_number ? ` · game ${c.game_number}, ${c.taps === 1 ? "1 tap" : `${c.taps} taps`}` : " · not played yet"}
                  </span>
                </span>
                <span className="flex flex-wrap gap-1.5 text-xs">
                  <Badge tone={c.blood.value < c.blood.most ? "blood" : "mist"}>
                    Blood {c.blood.value}/{c.blood.most}
                  </Badge>
                  <Badge tone={c.willpower.value < c.willpower.most ? "gold" : "mist"}>
                    Willpower {c.willpower.value}/{c.willpower.most}
                  </Badge>
                  <Badge tone={c.health_marked ? "blood" : "mist"}>
                    Health {c.health_boxes - c.health_marked}/{c.health_boxes}
                  </Badge>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="After the game">
        <p className="mb-3 text-sm text-mist">
          Resetting puts every character's trackers back for the next game. Each game's log is kept, under Past games on their Play View.
        </p>
        {asking ? (
          <div className="flex flex-wrap gap-2">
            <Button variant="danger" disabled={reset.isPending} onClick={() => reset.mutate(undefined)}>
              Reset everyone for the next game
            </Button>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setAsking(true)}>
            Reset everyone…
          </Button>
        )}
        {done !== null && <Notice>{done === 1 ? "1 character was reset." : `${done} characters were reset.`}</Notice>}
        <ErrorText error={reset.error} />
      </Card>
    </div>
  );
}
