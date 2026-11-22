import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "react-router";
import { api, unwrap } from "../../api/client";
import { useClanName } from "../../components/ClanNames";
import type { CharacterOut, TroupeOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { CardHeading } from "../../components/Headings";
import { AtHandle } from "../../components/PersonPicker";
import { Badge, Card, Loading } from "../../components/ui";
import { LinkButton } from "../../components/LinkButton";
import { joinPath } from "../directory";
import { newPlayersText } from "./profile";

/** A long troupe name wraps the button's words onto a second line. */
const WRAPS = "py-2 text-center";

/**
 * How to play in a troupe, for someone who doesn't yet: build a new character
 * for it, or bring one they have and ask to join. Hidden from its staff and from
 * players with a character at home here; a player whose character has asked to
 * join is told it waits for the storytellers.
 */
export function PlayHere({ troupe }: { troupe: TroupeOut }) {
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  const profile = useQuery({
    queryKey: ["troupe-profile", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupe.id } } })),
  });
  if (!characters.data) return null;
  const active = characters.data.filter((c) => c.status === "active");
  if (active.some((c) => c.home_troupe_id === troupe.id)) return null;

  const waiting = active.filter((c) => c.asking_troupe_id === troupe.id);
  if (waiting.length)
    return (
      <Card title="Waiting for the storytellers" className="mb-6 border-gold/40">
        <ul className="flex flex-col gap-2 text-sm">
          {waiting.map((c) => (
            <li key={c.id}>
              <Link to={`/characters/${c.id}/troupes`} className="text-gold hover:underline">
                {c.name}
              </Link>{" "}
              has asked to make {troupe.name} its home. Its storytellers will accept it or say what to change.
            </li>
          ))}
        </ul>
      </Card>
    );

  // Characters with no home troupe that this troupe takes, and that aren't asking another.
  const bring = active.filter((c) => !c.home_troupe_id && !c.asking_troupe_id && troupe.allowed_splats.includes(c.splat));
  const p = profile.data;
  const status = p ? newPlayersText(p.new_players) : null;

  return (
    <Card title="Play here" className="mb-6 border-gold/40">
      <div className="flex flex-col gap-4">
        {(status || p?.contact) && (
          <div className="flex flex-col gap-2 text-sm">
            {status && (
              <span>
                <Badge tone={p?.new_players === "welcoming" ? "gold" : "mist"}>{status}</Badge>
              </span>
            )}
            {p?.contact && (
              <p>
                <span className="text-mist">Ask about joining:</span>{" "}
                <Link to={`/players/${p.contact.id}`} className="text-gold hover:underline">
                  {p.contact.display_name}
                </Link>{" "}
                <AtHandle handle={p.contact.handle} />
              </p>
            )}
          </div>
        )}
        <div>
          <LinkButton to={`/characters?troupe=${troupe.id}`} className={WRAPS}>
            Build a new character for {troupe.name}
          </LinkButton>
          <p className="mt-1 text-xs text-mist">Its house rules apply while you build.</p>
        </div>
        {bring.length > 0 && (
          <div>
            <CardHeading>Or bring one you have</CardHeading>
            <ul className="mt-1 divide-y divide-ash">
              {bring.map((c) => (
                <Bring key={c.id} character={c} troupeId={troupe.id} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

/** One of the player's characters, with the way to ask this troupe to make it home. */
function Bring({ character: c, troupeId }: { character: CharacterOut; troupeId: string }) {
  const named = useClanName();
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <span className="flex min-w-0 items-center gap-3">
        <Avatar name={c.name} picture={c.picture} clan={c.clan} size="sm" />
        <span className="min-w-0 text-sm">
          {c.name}
          <span className="ml-2 text-mist capitalize">
            {c.splat}
            {c.clan && ` · ${named(c.clan)}`}
          </span>
        </span>
      </span>
      {c.creation_complete ? (
        <LinkButton variant="secondary" to={`/characters/${c.id}/troupes?home=${troupeId}`} className={WRAPS}>
          Ask to join
        </LinkButton>
      ) : (
        <Link to={`/characters/${c.id}/create`} className="text-sm text-gold hover:underline">
          Finish building it first
        </Link>
      )}
    </li>
  );
}

/**
 * Request to join, from a troupe's public profile (/troupes/<id>/join, #1192): on into
 * the ask-to-join flow with the troupe chosen (`joinPath`), building a new character
 * for it or choosing one to bring.
 */
export function JoinTroupe({ troupe }: { troupe: TroupeOut }) {
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  // Couldn't tell which characters there are: Play here, above, still offers the ways in.
  if (characters.error) return <Navigate to={`/troupes/${troupe.id}`} replace />;
  if (!characters.data) return <Loading />;
  return <Navigate to={joinPath(troupe, characters.data)} replace />;
}
