import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Textarea } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { roleLabel } from "./troupe/roles";

export function TroupesPage() {
  const me = useMe();
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });

  return (
    <>
      <PageTitle subtitle="Troupes run games and downtimes. Your characters join them from their own pages.">Troupes</PageTitle>
      <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
        <Card>
          {troupes.isPending ? (
            <Loading />
          ) : troupes.data?.length ? (
            <ul className="divide-y divide-ash">
              {troupes.data.map((t) => (
                <li key={t.id}>
                  <Link to={`/troupes/${t.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-gold">
                    <span>{t.name}</span>
                    {t.my_role && <Badge tone="gold">{roleLabel(t.my_role)}</Badge>}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No troupes yet.</Empty>
          )}
          <ErrorText error={troupes.error} />
        </Card>
        {me.data?.is_custodian && <NewTroupe />}
      </div>
    </>
  );
}

function NewTroupe() {
  const [form, setForm] = useState({ name: "", description: "", lead_email: "" });
  const create = useAction(async () => {
    await unwrap(api.POST("/api/troupes", { body: form }));
    setForm({ name: "", description: "", lead_email: "" });
  });
  return (
    <Card title="New troupe">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(undefined);
        }}
      >
        <Field label="Name">
          <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Description">
          <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Lead storyteller's email" hint="They need an account already.">
          <Input type="email" required value={form.lead_email} onChange={(e) => setForm({ ...form, lead_email: e.target.value })} />
        </Field>
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending}>
          Create troupe
        </Button>
      </form>
    </Card>
  );
}
