import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Select } from "../components/ui";
import { useAction } from "../hooks";

export function CharactersPage() {
  const navigate = useNavigate();
  const characters = useQuery({ queryKey: ["characters"], queryFn: () => unwrap(api.GET("/api/characters")) });
  const [name, setName] = useState("");
  const [splat, setSplat] = useState("vampire");
  const create = useAction(async () => {
    const character = await unwrap(api.POST("/api/characters", { body: { name, splat } }));
    navigate(`/characters/${character.id}`);
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
                    <span>
                      <span className="text-base">{c.name}</span>
                      <span className="ml-2 text-sm text-mist capitalize">{c.splat}</span>
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
            <Field label="Splat">
              <Select value={splat} onChange={(e) => setSplat(e.target.value)}>
                <option value="vampire">Vampire</option>
              </Select>
            </Field>
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
