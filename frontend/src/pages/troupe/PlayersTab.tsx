import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { AtHandle } from "../../components/PersonPicker";
import { Badge, Card, Empty, ErrorText, Input, Loading } from "../../components/ui";
import { roleLabel } from "./roles";
import { searchPlayers, troupePlayers } from "./troupePlayers";

/**
 * The troupe's players, those with an active character here, home or visiting:
 * who they are, which characters they bring, and their staff role if they have
 * one. Searched by player or character name.
 */
export function PlayersTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  // Shares the Characters tab's query.
  const roster = useQuery({ queryKey: ["roster", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", path)) });
  const staff = useQuery({ queryKey: ["staff", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", path)) });
  const [query, setQuery] = useState("");
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;

  const everyone = troupePlayers(roster.data);
  if (!everyone.length) return <Empty>No players have a character in this troupe yet.</Empty>;
  const shown = searchPlayers(everyone, query);
  const roles = new Map((staff.data ?? []).map((m) => [m.user_id, m.role]));

  return (
    <Card title="Players">
      <Input
        type="search"
        aria-label="Search players"
        placeholder="Player or character name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="mb-3 w-full"
      />
      <p className="mb-2 text-sm text-mist">
        {shown.length} of {everyone.length} players
      </p>
      {shown.length === 0 ? (
        <p className="py-3 text-sm text-mist">No players match.</p>
      ) : (
        <ul className="divide-y divide-ash">
          {shown.map((player) => {
            const role = roles.get(player.id);
            return (
              <li key={player.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <Link to={`/players/${player.id}`} className="font-medium hover:text-gold">
                  {player.name} {player.handle && <AtHandle handle={player.handle} />}
                </Link>
                {role && <Badge tone="gold">{roleLabel(role)}</Badge>}
                <ul className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
                  {player.characters.map((c) => (
                    <li key={c.character_id} className="flex items-center gap-1.5">
                      <Link to={`/characters/${c.character_id}`} className="hover:text-gold">
                        {c.character_name}
                      </Link>
                      {c.home ? <Badge tone="gold">Home</Badge> : <Badge>Visiting</Badge>}
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
