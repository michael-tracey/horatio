import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { DateInput } from "../../components/DateInput";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useDates, type Dates } from "../../dates";
import { useAction } from "../../hooks";
import { cycleLine, cycleStatus } from "./cycles";

/** A datetime input's value some days from now, on the storyteller's clock. */
function inDays(days: number, dates: Dates): string {
  return dates.toInput(new Date(Date.now() + days * 86_400_000));
}

export function CyclesTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const cycles = useQuery({ queryKey: ["cycles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/cycles", path)) });
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const dates = useDates();
  const [form, setForm] = useState({ name: "", closes_at: inDays(21, dates), grace_ends_at: inDays(28, dates) });
  // Until changed here, a new cycle earns the troupe's usual amount.
  const [completionXp, setCompletionXp] = useState<number | null>(null);
  const xp = completionXp ?? troupe.data?.downtime_xp ?? 2;
  // While a cycle is under way, the form for the next waits behind a button.
  const underWay = !!cycles.data?.some((c) => c.status === "open" || c.status === "closed");
  const [adding, setAdding] = useState(false);
  const showForm = !underWay || adding;
  const create = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/cycles", {
        ...path,
        body: {
          name: form.name,
          closes_at: dates.fromInput(form.closes_at).toISOString(),
          grace_ends_at: dates.fromInput(form.grace_ends_at).toISOString(),
          completion_xp: xp,
        },
      }),
    ),
  );

  return (
    <div className={showForm ? "grid gap-6 md:grid-cols-[2fr_1fr]" : "flex flex-col gap-6"}>
      <Card
        title="Downtime cycles"
        actions={
          !showForm && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              New cycle
            </Button>
          )
        }
      >
        {cycles.isPending ? (
          <Loading />
        ) : cycles.data?.length ? (
          <ul className="divide-y divide-ash">
            {cycles.data.map((c) => (
              <li key={c.id}>
                <Link to={`/cycles/${c.id}`} className="group flex items-center justify-between gap-2 py-3">
                  <span className="min-w-0">
                    <span className="block group-hover:text-gold">{c.name}</span>
                    <span className="block text-xs text-mist">{cycleLine(c, (at) => dates.dueDay(at))}</span>
                  </span>
                  <Badge tone={c.status === "open" ? "gold" : "mist"}>{cycleStatus(c.status)}</Badge>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No cycles yet.</Empty>
        )}
        <ErrorText error={cycles.error} />
      </Card>
      {showForm && (
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
            <Field label="Due" hint={`In your time zone (${dates.zoneName()}). Players see it in theirs.`}>
              <DateInput type="datetime-local" required value={form.closes_at} onChange={(e) => setForm({ ...form, closes_at: e.target.value })} />
            </Field>
            <Field label="Accepted until" hint="The grace period: late downtimes are still taken until then.">
              <DateInput type="datetime-local" required value={form.grace_ends_at} onChange={(e) => setForm({ ...form, grace_ends_at: e.target.value })} />
            </Field>
            <Field label="XP for completing" hint="Each character gets this when its downtime is submitted. The troupe's usual amount is on Starting points.">
              <Input type="number" min={0} max={100} required value={xp} onChange={(e) => setCompletionXp(Number(e.target.value))} className="w-24" />
            </Field>
            <ErrorText error={create.error} />
            <Button type="submit" disabled={create.isPending}>
              Create draft
            </Button>
            <p className="text-xs text-mist">It starts with a copy of the last cycle's form. Edit it, then open it.</p>
            {underWay && (
              <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
                Cancel
              </Button>
            )}
          </form>
        </Card>
      )}
    </div>
  );
}
