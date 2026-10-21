import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Textarea } from "../components/ui";
import { useDates } from "../dates";
import { useAction, useMe } from "../hooks";
import { roleLabel } from "./troupe/roles";
import { requestStatus } from "./troupeRequests";

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
        {me.data?.is_custodian ? (
          <NewTroupe />
        ) : (
          <div className="flex flex-col gap-6">
            <AskForTroupe />
            <MyRequests />
          </div>
        )}
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

/** Anyone may ask the custodian for a troupe of their own, which they would lead. */
function AskForTroupe() {
  const blank = { name: "", description: "", note: "" };
  const [form, setForm] = useState(blank);
  const ask = useAction(async () => {
    await unwrap(api.POST("/api/troupe-requests", { body: form }));
    setForm(blank);
  });
  return (
    <Card title="Ask for a new troupe">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          ask.mutate(undefined);
        }}
      >
        <p className="text-sm text-mist">The custodian makes troupes. If they approve, you will be its lead storyteller.</p>
        <Field label="Troupe name">
          <Input required maxLength={200} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Description" hint="Optional: the game, its setting, where it meets.">
          <Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <Field label="Note to the custodian" hint="Optional: anything they should know.">
          <Textarea rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Field>
        <ErrorText error={ask.error} />
        <Button type="submit" disabled={ask.isPending}>
          Send request
        </Button>
      </form>
    </Card>
  );
}

function MyRequests() {
  const dates = useDates();
  const mine = useQuery({ queryKey: ["troupe-requests", "mine"], queryFn: () => unwrap(api.GET("/api/troupe-requests/mine")) });
  const withdraw = useAction((id: string) => unwrap(api.DELETE("/api/troupe-requests/{request_id}", { params: { path: { request_id: id } } })));
  const shown = mine.data?.filter((r) => r.status !== "withdrawn") ?? [];
  if (!shown.length) return null;
  return (
    <Card title="Your requests" dense>
      <ul className="divide-y divide-ash text-sm">
        {shown.map((r) => (
          <li key={r.id} className="flex flex-col gap-1 py-2">
            <div className="flex items-center justify-between gap-2">
              {r.troupe_id ? (
                <Link to={`/troupes/${r.troupe_id}`} className="text-gold hover:underline">
                  {r.name}
                </Link>
              ) : (
                <span>{r.name}</span>
              )}
              <Badge tone={r.status === "approved" ? "gold" : r.status === "declined" ? "blood" : "mist"}>{requestStatus(r.status)}</Badge>
            </div>
            <span className="text-xs text-mist">
              Asked {dates.date(r.created_at)}
              {r.decided_at && `; ${requestStatus(r.status).toLowerCase()} ${dates.date(r.decided_at)}`}
            </span>
            {r.reason && <span className="text-xs text-mist">“{r.reason}”</span>}
            {r.status === "pending" && (
              <button type="button" className="self-start text-xs text-mist underline hover:text-parchment" disabled={withdraw.isPending} onClick={() => withdraw.mutate(r.id)}>
                Withdraw
              </button>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={withdraw.error} />
    </Card>
  );
}
