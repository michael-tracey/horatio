import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { AtHandle } from "../../components/PersonPicker";
import { Card, ErrorText, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import type { abilities } from "./roles";
import { XpRangeCard } from "./XpRange";

/**
 * The troupe at a glance: what it is, when it next plays, who leads it, which
 * sects and splats may join, and its XP floor and ceiling; for its staff, what is waiting
 * on them. The full profile is on the Profile tab.
 */
export function OverviewTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const base = `/troupes/${troupe.id}`;
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {can.staff && !troupe.archived && <WaitingCard troupeId={troupe.id} />}
      <Summary troupe={troupe} />
      <SectsCard troupe={troupe} canEdit={can.storyteller && !troupe.archived} />
      <SplatsCard troupe={troupe} canEdit={can.storyteller && !troupe.archived} />
      <div className="md:col-span-2">
        <XpRangeCard
          troupeId={troupe.id}
          canEdit={can.storyteller && !troupe.archived}
          link={
            can.running && (
              <Link to={`${base}/xp`} className="text-sm text-mist underline hover:text-parchment">
                Award XP
              </Link>
            )
          }
        />
      </div>
    </div>
  );
}

/** What waits on this staff member, one line per kind of work, each a link straight to it. */
function WaitingCard({ troupeId }: { troupeId: string }) {
  const waiting = useQuery({
    queryKey: ["waiting", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/waiting", { params: { path: { troupe_id: troupeId } } })),
    refetchInterval: 60_000,
  });
  return (
    <Card title="Waiting on you" className="md:col-span-2">
      {waiting.isPending ? (
        <Loading />
      ) : waiting.error ? (
        <ErrorText error={waiting.error} />
      ) : waiting.data.length === 0 ? (
        <p className="text-sm text-mist">Nothing waiting.</p>
      ) : (
        <ul className="divide-y divide-ash" aria-label="Waiting on you">
          {waiting.data.map((line) => (
            <li key={`${line.kind} ${line.link}`}>
              <Link to={line.link} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-gold">
                <span>{line.label}</span>
                <span className="min-w-8 rounded-full border border-gold/50 px-2 py-0.5 text-center text-xs text-gold tabular-nums">{line.count}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** The troupe's description, next game, schedule and lead, from its profile. */
function Summary({ troupe }: { troupe: TroupeOut }) {
  const dates = useDates();
  const profile = useQuery({
    queryKey: ["troupe-profile", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupe.id } } })),
  });
  const p = profile.data;
  const next = p?.games[0];
  return (
    <Card>
      <div className="flex flex-col gap-3 text-sm">
        {/* Not a heading: the page's own title already is. */}
        <p className="font-display text-lg text-gold">{troupe.name}</p>
        <p className="whitespace-pre-line">{troupe.description || <span className="text-mist">No description yet.</span>}</p>
        {profile.isPending ? (
          <Loading />
        ) : profile.error ? (
          <ErrorText error={profile.error} />
        ) : (
          p && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              <dt className="text-mist">Next game</dt>
              <dd>{next ? dates.gameStart(next.starts_at) : <span className="text-mist">None planned</span>}</dd>
              {p.schedule && (
                <>
                  <dt className="text-mist">Schedule</dt>
                  <dd>{p.schedule}</dd>
                </>
              )}
              <dt className="text-mist">Lead storyteller</dt>
              <dd>
                <Link to={`/players/${p.lead.id}`} className="hover:text-gold">
                  {p.lead.display_name}
                </Link>{" "}
                <AtHandle handle={p.lead.handle} />
              </dd>
            </dl>
          )
        )}
        <Link to={`/troupes/${troupe.id}/profile`} className="self-start text-mist underline hover:text-parchment">
          See the full profile
        </Link>
      </div>
    </Card>
  );
}

/** Which sects' player characters may join. None ticked means any may. */
function SectsCard({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", null],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: {} } })),
    staleTime: 5 * 60_000,
    enabled: canEdit,
  });
  const save = useAction((allowed_sects: string[]) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_sects } })),
  );
  const allowed = troupe.allowed_sects;
  const sects = (catalogue.data?.traits ?? []).filter((t) => t.category === "sect").map((t) => t.name);

  return (
    <Card title="Sects">
      {!canEdit ? (
        <p className="text-sm">{allowed.length ? `Player characters from ${allowed.join(", ")} may join.` : "Player characters from any sect may join."}</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm text-mist">Which sects may player characters join from? Leave all unticked to take any sect. NPCs are not limited.</legend>
          {sects.map((sect) => (
            <label key={sect} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allowed.includes(sect)}
                disabled={save.isPending}
                onChange={(e) => save.mutate(e.target.checked ? [...allowed, sect] : allowed.filter((s) => s !== sect))}
              />
              {sect}
            </label>
          ))}
          <ErrorText error={save.error ?? catalogue.error} />
        </fieldset>
      )}
    </Card>
  );
}

/** Which splats' player characters may join, and be built for the troupe: Vampire, Ghoul. At least one. */
function SplatsCard({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const splats = useQuery({
    queryKey: ["splats"],
    queryFn: () => unwrap(api.GET("/api/rules")),
    staleTime: 5 * 60_000,
  });
  const save = useAction((allowed_splats: string[]) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_splats } })),
  );
  const allowed = troupe.allowed_splats;
  const label = (splat: string) => splats.data?.find((s) => s.splat === splat)?.label ?? splat;
  const named = allowed.map(label);
  const listed = named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}` : named[0];

  return (
    <Card title="Splats">
      {!canEdit ? (
        <p className="text-sm">{listed} player characters may join.</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm text-mist">
            What may player characters be? New characters built for the troupe, and those joining it, must be one of these. NPCs are not limited.
          </legend>
          {(splats.data ?? []).map(({ splat, label }) => (
            <label key={splat} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allowed.includes(splat)}
                disabled={save.isPending || (allowed.length === 1 && allowed.includes(splat))}
                onChange={(e) => save.mutate(e.target.checked ? [...allowed, splat] : allowed.filter((s) => s !== splat))}
              />
              {label}
            </label>
          ))}
          <ErrorText error={save.error ?? splats.error} />
        </fieldset>
      )}
    </Card>
  );
}
