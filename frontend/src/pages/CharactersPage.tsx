import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Avatar } from "../components/Avatar";
import { clanNamed } from "../clanNames";
import type { TroupeOut } from "../api/types";
import { Badge, Button, Card, CountBubble, Empty, ErrorText, Field, Input, Loading, PageTitle, Select } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { useDates } from "../dates";
import { BuildFor } from "./character/BuildFor";
import { seenUpTo } from "./character/resultsSeen";
import { standing, waiting } from "./characterList";
import { splatsFor, useSplats } from "./character/splats";
import { roleLabel } from "./troupe/roles";
import { useWaiting, WaitingList } from "./troupe/WaitingList";
import { waitingTotal } from "./troupe/waiting";

export function CharactersPage() {
  const navigate = useNavigate();
  const me = useMe();
  const dates = useDates();
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  const [name, setName] = useState("");
  const [wanted, setSplat] = useState("vampire");
  // A troupe's "Play here" card links here with ?troupe=<id>, so the character is built for it.
  const [params] = useSearchParams();
  const [chosen, setBuildFor] = useState<string | null>(params.get("troupe"));
  // Only the splats the troupe built for takes; with none, every one.
  const splats = useSplats();
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  // A link to a troupe that isn't running (or isn't one) falls back to the book's rules.
  const buildFor = troupes.data && !troupes.data.some((t) => t.id === chosen) ? null : chosen;
  const troupe = troupes.data?.find((t) => t.id === buildFor);
  // Staff land here too: the troupes they run come first while they have no characters of their own. The welcome is for new players.
  const staff = !!me.data?.is_custodian || !!troupes.data?.some((t) => t.my_role);
  const running = (troupes.data ?? []).filter((t) => t.my_role && !t.archived);
  const troupesFirst = running.length > 0 && characters.data?.length === 0;
  const offered = splatsFor(splats.data ?? [], troupe);
  const splat = offered.some((s) => s.splat === wanted) ? wanted : (offered[0]?.splat ?? wanted);
  const create = useAction(async () => {
    const character = await unwrap(api.POST("/api/characters", { body: { name, splat, building_troupe_id: buildFor } }));
    navigate(`/characters/${character.id}/create`);
  });

  const yourTroupes = running.length > 0 && <YourTroupes troupes={running} heading={!troupesFirst} />;
  return (
    <>
      {troupesFirst ? (
        <PageTitle subtitle="The troupes you run, and what is waiting on you in each.">Your troupes</PageTitle>
      ) : (
        <PageTitle subtitle="Characters you play. Build one here, then bring it to a troupe.">Your characters</PageTitle>
      )}
      <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
        <div className="flex min-w-0 flex-col gap-6">
          {troupesFirst && yourTroupes}
          <Card title={troupesFirst ? "Your characters" : undefined}>
            {characters.isPending ? (
              <Loading />
            ) : characters.data?.length ? (
              <ul className="divide-y divide-ash">
                {characters.data.map((c) => (
                  <li key={c.id}>
                    <Link to={`/characters/${c.id}`} className="flex items-center gap-3 py-3 hover:text-gold">
                      <Avatar name={c.name} picture={c.picture} clan={c.clan} />
                      <span className="min-w-0">
                        <span className="text-base">{c.name}</span>
                        <span className="ml-2 text-sm text-mist capitalize">
                          {c.splat}
                          {/* As the troupe it plays in calls its clan. */}
                          {c.clan && ` · ${clanNamed(c.clan, c.assamite_name)}`}
                        </span>
                        <span className="mt-1 flex min-w-0 flex-wrap gap-1.5">
                          {[...standing(c), ...waiting(c, seenUpTo(c.id), dates)].map((n) => (
                            <Badge key={n.label} tone={n.tone} className="max-w-full truncate">
                              {n.label}
                            </Badge>
                          ))}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : troupes.isPending || me.isPending ? (
              <Loading />
            ) : staff ? (
              <Empty>No characters of your own yet. Build one under New character to play.</Empty>
            ) : (
              <Welcome troupe={troupe?.name} />
            )}
            <ErrorText error={characters.error} />
          </Card>
          {!troupesFirst && yourTroupes}
        </div>
        <Card title="New character">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate(undefined);
            }}
          >
            <Field label="Name">
              <Input required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <BuildFor value={buildFor} onChange={setBuildFor} newCharacter />
            <Field label="Splat" hint={troupe && offered.length === 1 ? `${troupe.name} takes ${offered[0]!.label.toLowerCase()} characters only.` : undefined}>
              <Select value={splat} onChange={(e) => setSplat(e.target.value)}>
                {offered.map((s) => (
                  <option key={s.splat} value={s.splat}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </Field>
            <ErrorText error={splats.error} />
            <ErrorText error={create.error} />
            <Button type="submit" disabled={create.isPending}>
              Create
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}

/** For staff: each troupe they run, with what is waiting on them there, from the same lines as its About page. */
function YourTroupes({ troupes, heading }: { troupes: TroupeOut[]; heading: boolean }) {
  return (
    <section aria-label="Your troupes" className="flex flex-col gap-6">
      {/* Below the person's own characters it needs a heading; first, the page's title is its heading. */}
      {heading && <h2 className="font-display text-lg text-gold">Your troupes</h2>}
      {troupes.map((t) => (
        <TroupeWaiting key={t.id} troupe={t} />
      ))}
    </section>
  );
}

function TroupeWaiting({ troupe }: { troupe: TroupeOut }) {
  const waiting = useWaiting(troupe.id);
  const total = waitingTotal(waiting.data);
  return (
    <Card
      title={
        <Link to={`/troupes/${troupe.id}`} className="inline-flex items-center gap-2 hover:text-gold">
          {troupe.portrait && <Avatar name={troupe.name} picture={troupe.portrait} size="sm" />}
          {troupe.name}
          <CountBubble count={total} label="waiting" />
        </Link>
      }
      actions={troupe.my_role && <Badge tone="gold">{roleLabel(troupe.my_role)}</Badge>}
    >
      {waiting.isPending ? (
        <Loading />
      ) : waiting.error ? (
        <ErrorText error={waiting.error} />
      ) : waiting.data.length === 0 ? (
        <p className="text-sm text-mist">Nothing waiting.</p>
      ) : (
        <WaitingList lines={waiting.data} label={`Waiting on you in ${troupe.name}`} />
      )}
    </Card>
  );
}

/** What a new player does first: find their troupe, build a character for it, and ask it to accept them. */
function Welcome({ troupe }: { troupe?: string }) {
  return (
    <section aria-label="Welcome" className="flex flex-col gap-3 py-2">
      <h2 className="text-lg text-gold">Welcome to Horatio</h2>
      <p className="text-sm text-mist">Horatio keeps your characters for the troupes you play in. Three steps to your first game:</p>
      <ol className="flex flex-col gap-3 text-sm">
        <Step n={1} title={troupe ? `Your troupe: ${troupe}` : "Find your troupe"}>
          {troupe ? (
            "Its house rules apply to the character you build."
          ) : (
            <>
              Your storytellers may have sent you its link, or look for it in{" "}
              <Link to="/troupes" className="text-gold underline">
                the troupe list
              </Link>
              . Its page shows how to play there.
            </>
          )}
        </Step>
        <Step n={2} title="Build a character for it">
          Give it a name under New character, choose its troupe, and Horatio walks you through the rest.
        </Step>
        <Step n={3} title="Ask the troupe to accept it">
          Once it is finished, ask to make the troupe its home from the character's Troupes tab. Its storytellers take it from there.
        </Step>
      </ol>
    </section>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-gold/60 text-gold">
        {n}
      </span>
      <span className="min-w-0">
        <span className="block text-parchment">{title}</span>
        <span className="block text-mist">{children}</span>
      </span>
    </li>
  );
}
