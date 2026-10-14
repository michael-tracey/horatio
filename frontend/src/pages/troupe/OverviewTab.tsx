import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Textarea } from "../../components/ui";
import { useAction, useMe } from "../../hooks";
import type { abilities } from "./roles";

export function OverviewTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const me = useMe();
  const navigate = useNavigate();
  const path = { params: { path: { troupe_id: troupe.id } } };
  const [name, setName] = useState(troupe.name);
  const [description, setDescription] = useState(troupe.description);
  const [leadEmail, setLeadEmail] = useState("");

  const save = useAction(() => unwrap(api.PATCH("/api/troupes/{troupe_id}", { ...path, body: { name, description } })));
  const archive = useAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}", path));
    navigate("/troupes");
  });
  const appoint = useAction(() => unwrap(api.PUT("/api/troupes/{troupe_id}/lead", { ...path, body: { email: leadEmail } })));

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="About">
        <p className="text-sm whitespace-pre-line">{troupe.description || "No description yet."}</p>
      </Card>
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
      {me.data?.is_custodian && (
        <Card title="Lead storyteller">
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              appoint.mutate(undefined);
            }}
          >
            <Field label="Appoint a new lead by email">
              <Input type="email" required value={leadEmail} onChange={(e) => setLeadEmail(e.target.value)} />
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
