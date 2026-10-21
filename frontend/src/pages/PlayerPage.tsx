import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { PlayerOut } from "../api/types";
import { Badge, Card, Empty, ErrorText, Loading, PageTitle } from "../components/ui";
import { useDates } from "../dates";
import { useMe } from "../hooks";
import { ResetPassword } from "./custodian/ResetPassword";
import { memberSince } from "./players";

/** Who a player is: anyone signed in may look. The custodian can also make a reset link here. */
export function PlayerPage() {
  const { userId = "" } = useParams();
  const me = useMe();
  const dates = useDates();
  const player = useQuery({
    queryKey: ["player", userId],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: userId } } })),
  });
  if (player.isPending) return <Loading />;
  if (player.error) return <ErrorText error={player.error} />;
  const p = player.data;
  const mine = me.data?.id === p.id;

  return (
    <>
      <PageTitle
        subtitle={`@${p.handle} · Member since ${memberSince(p.member_since, dates)}`}
        actions={
          mine && (
            <Link to="/account" className="text-sm text-gold underline">
              Edit your profile
            </Link>
          )
        }
      >
        {p.display_name} {p.is_custodian && <Badge tone="gold">custodian</Badge>}
      </PageTitle>
      <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-6">
          <Card title="About">
            {p.bio ? <p className="text-sm leading-relaxed whitespace-pre-line">{p.bio}</p> : <Empty>No bio yet.</Empty>}
          </Card>
          <Characters player={p} />
        </div>
        <div className="flex flex-col gap-6">
          <Contact player={p} />
          {me.data?.is_custodian && !mine && (
            <Card title="Password">
              <ResetPassword player={p} />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function Contact({ player }: { player: PlayerOut }) {
  if (!player.discord_handle && !player.links.length && !player.email) return null;
  return (
    <Card title="Elsewhere">
      <dl className="flex flex-col gap-2 text-sm">
        {player.discord_handle && (
          <div>
            <dt className="text-xs text-mist">Discord</dt>
            <dd>@{player.discord_handle}</dd>
          </div>
        )}
        {player.email && (
          <div>
            <dt className="text-xs text-mist">Email (not shown to other players)</dt>
            <dd className="break-all">{player.email}</dd>
          </div>
        )}
        {player.links.map((link) => (
          <div key={link.url}>
            <dt className="text-xs text-mist">{link.label}</dt>
            <dd className="break-all">
              <a href={link.url} target="_blank" rel="noopener noreferrer nofollow ugc" className="text-gold underline">
                {link.url.replace(/^https?:\/\//, "")}
              </a>
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Characters({ player }: { player: PlayerOut }) {
  if (!player.characters.length) return null;
  return (
    <Card title="Characters you can see">
      <ul className="divide-y divide-ash text-sm">
        {player.characters.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-2 py-2">
            <Link to={`/characters/${c.id}`} className="hover:text-gold">
              {c.name}
            </Link>
            <span className="flex items-center gap-2 text-mist">
              {c.home_troupe ?? "no home troupe"}
              {c.retired && <Badge>retired</Badge>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
