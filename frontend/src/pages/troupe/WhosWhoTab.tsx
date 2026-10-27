import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { WhosWhoEntry } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Badge, Empty, ErrorText, Input, Loading, Select } from "../../components/ui";
import { NO_FILTER, clanText, filterChoices, sections, type Section, type WhosWhoFilter } from "./whosWho";

/**
 * The troupe's Who's Who (issue #264): its active characters for its players and
 * staff, as cards. The court in rank order, one section per clan with a seat, Other
 * for the clans without one, and who is no longer with us, with a jump list, a
 * search by character, player or title, and filters by clan and sect.
 */
export function WhosWhoTab({ troupeId }: { troupeId: string }) {
  const whosWho = useQuery({
    queryKey: ["whos-who", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/whos-who", { params: { path: { troupe_id: troupeId } } })),
  });
  const [filter, setFilter] = useState<WhosWhoFilter>(NO_FILTER);
  const { hash } = useLocation();
  const loaded = !!whosWho.data;
  // A link to one character's entry (from the Play View) scrolls to it once it is there.
  useEffect(() => {
    if (loaded && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "center" });
  }, [loaded, hash]);

  if (whosWho.isPending) return <Loading />;
  if (whosWho.error) return <ErrorText error={whosWho.error} />;
  const data = whosWho.data;
  const shown = sections(data, filter);
  const choices = filterChoices(data);
  const filtered = filter.query.trim() !== "" || !!filter.clan || !!filter.sect;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-mist">The troupe’s characters, for its players and staff. It is never public.</p>
        <a
          href={`/print/troupes/${troupeId}/whos-who`}
          target="_blank"
          rel="noopener"
          className="inline-flex min-h-9 items-center rounded-md border border-ash px-3 text-sm text-parchment hover:border-gold hover:text-gold"
        >
          Print
        </a>
      </div>
      <div className="flex flex-wrap gap-3">
        <Input
          aria-label="Search the Who's Who"
          placeholder="Character, player or title"
          className="min-w-0 flex-1 basis-56"
          value={filter.query}
          onChange={(e) => setFilter({ ...filter, query: e.target.value })}
        />
        <Select aria-label="Clan" className="w-auto" value={filter.clan} onChange={(e) => setFilter({ ...filter, clan: e.target.value })}>
          <option value="">Every clan</option>
          {choices.clans.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
        {choices.sects.length > 1 && (
          <Select aria-label="Sect" className="w-auto" value={filter.sect} onChange={(e) => setFilter({ ...filter, sect: e.target.value })}>
            <option value="">Every sect</option>
            {choices.sects.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        )}
      </div>
      {shown.length > 1 && (
        <nav aria-label="Jump to" className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
          {shown.map((s) => (
            <a key={s.id} href={`#${s.id}`} className="text-mist underline hover:text-gold">
              {s.title}
            </a>
          ))}
        </nav>
      )}
      {shown.length === 0 && <Empty>{filtered ? "No one matches." : "No one yet."}</Empty>}
      {shown.map((s) => (
        <WhosWhoSection key={s.id} section={s} seated={data.seated} />
      ))}
    </div>
  );
}

function WhosWhoSection({ section, seated }: { section: Section; seated: string[] | null }) {
  const headingId = `${section.id}-heading`;
  return (
    <section id={section.id} aria-labelledby={headingId} className="scroll-mt-4">
      <h2 id={headingId} className="mb-1 text-lg text-gold">
        {section.title}
      </h2>
      {section.kind === "court" && <p className="mb-2 text-xs text-mist">Everyone holding a title here, highest first.</p>}
      {section.kind === "other" && (
        <p className="mb-2 text-xs text-mist">
          Clans with no seat at court.{seated && ` Only the ${andList(seated)} have a Primogen here.`}
        </p>
      )}
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {section.entries.map((e) => (
          // Every character is in one clan section or Other: the place a link to it goes.
          <li key={e.character_id} id={section.kind === "clan" || section.kind === "other" ? `c-${e.character_id}` : undefined} className="scroll-mt-4">
            <EntryCard entry={e} kind={section.kind} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** "Brujah, Toreador and Ventrue". */
function andList(items: string[]): string {
  return items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}` : (items[0] ?? "");
}

/** One character: who it is, who plays it, what it holds here, and what others can see. */
function EntryCard({ entry: e, kind }: { entry: WhosWhoEntry; kind: Section["kind"] }) {
  return (
    <article aria-label={e.name} className="flex h-full gap-3 rounded-lg border border-ash bg-dusk p-3">
      <Avatar name={e.name} picture={e.picture} clan={e.clan} size="md" />
      <div className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-display text-base text-parchment">{e.name}</span>
          {e.pronouns && <span className="text-xs text-mist">({e.pronouns})</span>}
        </div>
        <span className="text-mist">
          {clanText(e.clan)} · {e.social_age}
        </span>
        <span>
          {e.player_id ? (
            <>
              Played by{" "}
              <Link to={`/players/${e.player_id}`} className="text-parchment underline hover:text-gold">
                {e.player_name}
              </Link>
              {e.player_pronouns && <span className="text-xs text-mist"> ({e.player_pronouns})</span>}
            </>
          ) : (
            <Badge>NPC</Badge>
          )}
        </span>
        {(e.titles.length > 0 || e.visiting) && (
          <span className="flex flex-wrap gap-1">
            {e.titles.map((t) => (
              <Badge key={t} tone="gold">
                {t}
              </Badge>
            ))}
            {e.visiting && <Badge>{e.visiting_from ? `Visiting from ${e.visiting_from}` : "Visiting"}</Badge>}
          </span>
        )}
        {kind === "other" && <span className="text-mist">Represented by: {e.represented_by ?? "nobody yet"}</span>}
        {kind === "departed" && e.left_reason && <span className="text-mist">{e.left_reason}</span>}
        {(e.visible.length > 0 || e.bans.length > 0 || e.negative.length > 0) && (
          <ul aria-label={`What others see of ${e.name}`} className="mt-1 flex flex-col gap-0.5 border-t border-ash pt-1 text-xs">
            {e.visible.map((v) => (
              <li key={v}>{v}</li>
            ))}
            {e.bans.map((b) => (
              <li key={b} className="text-blood-bright">
                {b}
              </li>
            ))}
            {e.negative.map((n) => (
              <li key={n} className="text-blood-bright">
                Negative status: {n}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
