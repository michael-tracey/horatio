import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { ErrorText } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { PAYMENTS_NOTE } from "./GameXpSettings";

/**
 * For players, where the troupe lets them (issue #438): the games just played whose XP
 * is still to award, to mark a character who missed one absentee. An absentee game
 * never counts as attended, and gets the troupe's absentee XP.
 */
export function MissedGames({ troupeId }: { troupeId: string }) {
  const dates = useDates();
  const toast = useToast();
  const missed = useQuery({
    queryKey: ["missed-games", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/games/missed", { params: { path: { troupe_id: troupeId } } })),
  });
  const mark = useAction(
    async ({ gameId, characterId, on }: { gameId: string; characterId: string; on: boolean }) => {
      const params = { params: { path: { troupe_id: troupeId, game_id: gameId, character_id: characterId } } };
      const done = await unwrap(
        on ? api.PUT("/api/troupes/{troupe_id}/games/{game_id}/absentee/{character_id}", params) : api.DELETE("/api/troupes/{troupe_id}/games/{game_id}/absentee/{character_id}", params),
      );
      toast({ message: on ? `Marked absentee: ${done.character_name}` : `No longer absentee: ${done.character_name}` });
    },
    [["missed-games", troupeId]],
  );
  if (!missed.data?.length) return null;
  return (
    <section aria-labelledby="missed-games" className="mt-4 border-t border-ash pt-3">
      <h3 id="missed-games" className="text-sm text-mist">
        Missed a game?
      </h3>
      <p className="text-xs text-mist">Mark a character absentee for a game it missed, until the game's XP is awarded. {PAYMENTS_NOTE}</p>
      <ul aria-label="Games you can mark absentee" className="mt-2 flex flex-col gap-2 text-sm">
        {missed.data.map((g) => (
          <li key={g.game_id} className="flex flex-col gap-1">
            <span className="text-parchment">{dates.gameStart(g.starts_at)}</span>
            <span className="flex flex-wrap gap-x-4 gap-y-1">
              {g.characters.map((c) => (
                <label key={c.id} className="flex min-h-8 items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={g.absentee.includes(c.id)}
                    disabled={mark.isPending}
                    onChange={(e) => mark.mutate({ gameId: g.game_id, characterId: c.id, on: e.target.checked })}
                  />
                  {c.name} absentee
                </label>
              ))}
            </span>
          </li>
        ))}
      </ul>
      <ErrorText error={mark.error} />
    </section>
  );
}
