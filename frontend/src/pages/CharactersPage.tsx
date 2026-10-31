import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Avatar } from "../components/Avatar";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Select } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { BuildFor } from "./character/BuildFor";
import { splatsFor, useSplats } from "./character/splats";

export function CharactersPage() {
  const navigate = useNavigate();
  const me = useMe();
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
  // Staff land here too, with no characters of their own; the welcome is for new players.
  const staff = !!me.data?.is_custodian || !!troupes.data?.some((t) => t.my_role);
  const offered = splatsFor(splats.data ?? [], troupe);
  const splat = offered.some((s) => s.splat === wanted) ? wanted : (offered[0]?.splat ?? wanted);
  const create = useAction(async () => {
    const character = await unwrap(api.POST("/api/characters", { body: { name, splat, building_troupe_id: buildFor } }));
    navigate(`/characters/${character.id}/create`);
  });

  return (
    <>
      <PageTitle subtitle="Characters you play. Build one here, then bring it to a troupe.">Your characters</PageTitle>
      <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
        <Card>
          {characters.isPending ? (
            <Loading />
          ) : characters.data?.length ? (
            <ul className="divide-y divide-ash">
              {characters.data.map((c) => (
                <li key={c.id}>
                  <Link to={`/characters/${c.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-gold">
                    <span className="flex min-w-0 items-center gap-3">
                      <Avatar name={c.name} picture={c.picture} clan={c.clan} />
                      <span className="min-w-0">
                        <span className="text-base">{c.name}</span>
                        <span className="ml-2 text-sm text-mist capitalize">
                          {c.splat}
                          {c.clan && ` · ${c.clan}`}
                        </span>
                      </span>
                    </span>
                    <Badge tone={c.status === "active" ? "gold" : c.status === "retired" ? "mist" : "blood"}>{c.status}</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          ) : troupes.isPending || me.isPending ? (
            <Loading />
          ) : staff ? (
            <Empty>No characters yet.</Empty>
          ) : (
            <Welcome troupe={troupe?.name} />
          )}
          <ErrorText error={characters.error} />
        </Card>
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
