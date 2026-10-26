import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { Avatar } from "../components/Avatar";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Select } from "../components/ui";
import { useAction } from "../hooks";
import { BuildFor } from "./character/BuildFor";
import { splatsFor, useSplats } from "./character/splats";

export function CharactersPage() {
  const navigate = useNavigate();
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  const [name, setName] = useState("");
  const [wanted, setSplat] = useState("vampire");
  const [buildFor, setBuildFor] = useState<string | null>(null);
  // Only the splats the troupe built for takes; with none, every one.
  const splats = useSplats();
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const troupe = troupes.data?.find((t) => t.id === buildFor);
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
          ) : (
            <Empty>No characters yet.</Empty>
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
