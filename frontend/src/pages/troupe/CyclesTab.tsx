import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

function inDays(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function CyclesTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const cycles = useQuery({ queryKey: ["cycles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/cycles", path)) });
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [form, setForm] = useState({ name: "", closes_at: inDays(21), grace_ends_at: inDays(28) });
  // Until changed here, a new cycle earns the troupe's usual amount.
  const [completionXp, setCompletionXp] = useState<number | null>(null);
  const xp = completionXp ?? troupe.data?.downtime_xp ?? 2;
  const create = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/cycles", {
        ...path,
        body: {
          name: form.name,
          closes_at: new Date(form.closes_at).toISOString(),
          grace_ends_at: new Date(form.grace_ends_at).toISOString(),
          completion_xp: xp,
        },
      }),
    ),
  );

  return (
    <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <Card title="Downtime cycles">
        {cycles.isPending ? (
          <Loading />
        ) : cycles.data?.length ? (
          <ul className="divide-y divide-ash">
            {cycles.data.map((c) => (
              <li key={c.id}>
                <Link to={`/cycles/${c.id}`} className="flex items-center justify-between gap-2 py-3 hover:text-gold">
                  <span>{c.name}</span>
                  <Badge tone={c.status === "open" ? "gold" : "mist"}>{c.status}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No cycles yet.</Empty>
        )}
        <ErrorText error={cycles.error} />
      </Card>
      <Card title="New cycle">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(undefined);
          }}
        >
          <Field label="Name">
            <Input required placeholder="November 2026" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Due">
            <Input type="datetime-local" required value={form.closes_at} onChange={(e) => setForm({ ...form, closes_at: e.target.value })} />
          </Field>
          <Field label="Accepted until" hint="The grace period: late downtimes are still taken until then.">
            <Input type="datetime-local" required value={form.grace_ends_at} onChange={(e) => setForm({ ...form, grace_ends_at: e.target.value })} />
          </Field>
          <Field label="XP for completing" hint="Each character gets this when its downtime is submitted. The troupe's usual amount is on Starting points.">
            <Input type="number" min={0} max={100} required value={xp} onChange={(e) => setCompletionXp(Number(e.target.value))} className="w-24" />
          </Field>
          <ErrorText error={create.error} />
          <Button type="submit" disabled={create.isPending}>
            Create draft
          </Button>
          <p className="text-xs text-mist">It starts with a copy of the last cycle's form. Edit it, then open it.</p>
        </form>
      </Card>
    </div>
  );
}
