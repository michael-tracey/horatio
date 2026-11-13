import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { PersonPicker } from "../../components/PersonPicker";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { ArchivedTroupesTab } from "./ArchivedTroupesTab";
import { TroupeRequestsTab } from "./TroupeRequestsTab";

/**
 * Everything the custodian does with troupes as a whole, in one place (#759):
 * setting one up with its lead storyteller, changing a troupe's lead, the new
 * troupes people ask for, and the troupes that have been archived. The old
 * Troupe requests and Archived troupes addresses land on their sections here.
 */
export function TroupeManagementTab() {
  const { hash } = useLocation();
  // An address with #requests or #archived (an old link, a notification) opens at that section.
  useEffect(() => {
    if (!hash) return;
    document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [hash]);

  return (
    <div className="flex flex-col gap-8">
      {/* The troupes beside a narrow New troupe column, as the Troupes page had it:
          there the person picker's list opens over the field's hint, not the button. */}
      <div className="grid gap-8 md:grid-cols-[2fr_1fr]">
        <Section id="troupes" title="Troupes">
          <RunningTroupes />
        </Section>
        <Section id="new" title="New troupe">
          <NewTroupe />
        </Section>
      </div>
      <Section id="requests" title="Requests">
        <TroupeRequestsTab />
      </Section>
      <Section id="archived" title="Archived troupes">
        <ArchivedTroupesTab />
      </Section>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="flex scroll-mt-4 flex-col gap-3">
      <h2 id={`${id}-heading`} className="font-display text-xl text-parchment">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** The custodian sets up a troupe and names its lead storyteller, who needs an account already. */
function NewTroupe() {
  const [form, setForm] = useState({ name: "", description: "", lead_handle: "" });
  const create = useAction(async () => {
    await unwrap(api.POST("/api/troupes", { body: form }));
    setForm({ name: "", description: "", lead_handle: "" });
  });
  return (
    <Card>
      <form
        className="flex flex-col gap-3"
        aria-label="New troupe"
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
        <Field label="Lead storyteller" hint="Pick them from the list, or type a name or handle to find them. They need an account already.">
          <PersonPicker required value={form.lead_handle} onChange={(lead_handle) => setForm({ ...form, lead_handle })} />
        </Field>
        <ErrorText error={create.error} />
        <Button type="submit" disabled={create.isPending}>
          Create troupe
        </Button>
      </form>
    </Card>
  );
}

/** The troupes still running, each with a way to appoint a new lead storyteller. */
function RunningTroupes() {
  const troupes = useQuery({ queryKey: ["troupes", "management"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  if (troupes.isPending) return <Loading />;
  if (troupes.error) return <ErrorText error={troupes.error} />;
  if (!troupes.data.length) return <Empty>No troupes yet.</Empty>;
  return (
    <Card>
      <ul className="divide-y divide-ash" aria-label="Troupes">
        {troupes.data.map((t) => (
          <RunningTroupe key={t.id} troupe={t} />
        ))}
      </ul>
    </Card>
  );
}

function RunningTroupe({ troupe: t }: { troupe: TroupeOut }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <Link to={`/troupes/${t.id}`} className="font-medium text-parchment hover:text-gold">
        {t.name}
      </Link>
      {/* Named by its text, not an aria-label: a label holding "lead storyteller" on
          every row would answer to the New troupe form's own field label. */}
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Change lead…<span className="sr-only"> for {t.name}</span>
      </Button>
      {/* Only while open, as a closed dialog's title still labels it (see above). */}
      {open && (
        <Dialog title={`New lead for ${t.name}`} open onClose={() => setOpen(false)}>
          <AppointLead troupe={t} onDone={() => setOpen(false)} />
        </Dialog>
      )}
    </li>
  );
}

/**
 * Appoints a new lead, as the troupe's own Staff tab does: the one replaced leaves
 * the staff. The current lead is asked for only once the dialog is open.
 */
function AppointLead({ troupe, onDone }: { troupe: TroupeOut; onDone: () => void }) {
  const [handle, setHandle] = useState("");
  const staff = useQuery({
    queryKey: ["staff", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", { params: { path: { troupe_id: troupe.id } } })),
  });
  const lead = staff.data?.find((m) => m.role === "lead_storyteller")?.display_name;
  const appoint = useAction(async () => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/lead", { params: { path: { troupe_id: troupe.id } }, body: { handle } }));
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        appoint.mutate(undefined);
      }}
    >
      <p className="text-sm text-mist">Now: {lead ?? "…"}</p>
      <Field label="New lead" hint="Pick them from the list, or type a name or handle to find them.">
        <PersonPicker required value={handle} onChange={setHandle} />
      </Field>
      <p className="text-sm text-mist">
        {lead ?? "The current lead"} will leave the staff, with no role in the troupe. To keep them on, add them back on the troupe's Staff tab once the new lead
        is appointed.
      </p>
      <ErrorText error={appoint.error ?? staff.error} />
      <Button type="submit" disabled={appoint.isPending}>
        Appoint
      </Button>
    </form>
  );
}
