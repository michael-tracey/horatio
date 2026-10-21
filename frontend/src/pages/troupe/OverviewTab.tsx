import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { PersonPicker } from "../../components/PersonPicker";
import { Button, Card, ErrorText, Field, Input, Textarea } from "../../components/ui";
import { useAction, useMe } from "../../hooks";
import { TroupeProfileSection } from "./ProfileEditor";
import type { abilities } from "./roles";
import { XpRangeCard } from "./XpRange";

export function OverviewTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const me = useMe();
  const navigate = useNavigate();
  const path = { params: { path: { troupe_id: troupe.id } } };
  const [name, setName] = useState(troupe.name);
  const [description, setDescription] = useState(troupe.description);
  const [leadHandle, setLeadHandle] = useState("");

  const save = useAction(() => unwrap(api.PATCH("/api/troupes/{troupe_id}", { ...path, body: { name, description } })));
  const archive = useAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}", path));
    navigate("/troupes");
  });
  const appoint = useAction(() => unwrap(api.PUT("/api/troupes/{troupe_id}/lead", { ...path, body: { handle: leadHandle } })));

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="md:col-span-2">
        <TroupeProfileSection troupe={troupe} />
      </div>
      {can.lead && !troupe.archived && (
        <Card title="Troupe settings">
          <div className="flex flex-col gap-3">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Description">
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            <ErrorText error={save.error ?? archive.error} />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => save.mutate(undefined)} disabled={save.isPending}>
                Save
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  if (window.confirm(`Archive ${troupe.name}? It closes to everyone; its history is kept.`)) archive.mutate(undefined);
                }}
              >
                Archive troupe
              </Button>
            </div>
          </div>
        </Card>
      )}
      <SectsCard troupe={troupe} canEdit={can.storyteller && !troupe.archived} />
      <XpRangeCard troupeId={troupe.id} canEdit={false} />
      {me.data?.is_custodian && (
        <Card title="Lead storyteller">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              appoint.mutate(undefined);
            }}
          >
            <Field label="Appoint a new lead" hint="Type a handle or a name to find them.">
              <PersonPicker required value={leadHandle} onChange={setLeadHandle} />
            </Field>
            <ErrorText error={appoint.error} />
            <Button type="submit" variant="secondary">
              Appoint
            </Button>
          </form>
        </Card>
      )}
    </div>
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
