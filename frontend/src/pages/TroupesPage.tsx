import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import type { TroupeOut } from "../api/types";
import { Avatar } from "../components/Avatar";
import { EmptyState } from "../components/EmptyState";
import { PersonPicker } from "../components/PersonPicker";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTitle, Textarea } from "../components/ui";
import { useDates } from "../dates";
import { useAction, useMe } from "../hooks";
import { useSuspendedIds } from "./custodian/Suspension";
import { newPlayersText } from "./troupe/profile";
import { roleLabel } from "./troupe/roles";
import { excerpt, matches, ownFirst, SEARCH_FROM } from "./troupeList";
import { requestStatus } from "./troupeRequests";

export function TroupesPage() {
  const me = useMe();
  // A key of its own, so the page asks afresh as it opens: the list another page
  // asked for earlier can still be on its way, and lacks a troupe made since.
  const troupes = useQuery({ queryKey: ["troupes", "page"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const suspended = useSuspendedIds(!!me.data?.is_custodian);
  const [query, setQuery] = useState("");
  const all = ownFirst(troupes.data ?? []);
  const shown = all.filter((t) => matches(t, query));

  const list = (
    <Card>
      {troupes.isPending ? (
        <Loading />
      ) : all.length ? (
        <>
          {(all.length > SEARCH_FROM || query) && (
            <Input
              type="search"
              aria-label="Search troupes"
              placeholder="Name, place or description…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="mb-2 w-full"
            />
          )}
          {shown.length ? (
            <ul className="divide-y divide-ash">
              {shown.map((t) => (
                <li key={t.id}>
                  <TroupeRow troupe={t} leadSuspended={suspended.has(t.lead_user_id)} />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title={`No troupe matches “${query.trim()}”.`}
              action={
                <Button variant="secondary" onClick={() => setQuery("")}>
                  Show every troupe
                </Button>
              }
            />
          )}
        </>
      ) : (
        <Empty>No troupes yet.</Empty>
      )}
      <ErrorText error={troupes.error} />
    </Card>
  );

  return (
    <>
      <PageTitle subtitle="Troupes run games and downtimes. Your characters join them from their own pages.">Troupes</PageTitle>
      {me.data?.is_custodian ? (
        <div className="grid gap-6 md:grid-cols-[2fr_1fr]">
          {list}
          <NewTroupe />
        </div>
      ) : (
        <div className="flex max-w-3xl flex-col gap-6">
          {list}
          <MyRequests />
          <AskForTroupe />
        </div>
      )}
    </>
  );
}

/** One troupe in the list: what there is to choose it by, and whether it is the person's own. */
function TroupeRow({ troupe: t, leadSuspended }: { troupe: TroupeOut; leadSuspended: boolean }) {
  const about = excerpt(t.description);
  const newPlayers = newPlayersText(t.new_players);
  const playing = t.my_characters.length > 0;
  return (
    <Link to={`/troupes/${t.id}`} className="group flex items-start gap-3 py-3">
      <Avatar name={t.name} picture={t.portrait} size="sm" />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="font-medium text-parchment group-hover:text-gold">{t.name}</span>
          {t.place && <span className="text-xs text-mist">{t.place}</span>}
        </span>
        {about && <span className="line-clamp-2 text-sm text-mist">{about}</span>}
        {(playing || t.my_role || newPlayers || leadSuspended) && (
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {playing && (
              <>
                <Badge tone="gold">You play here</Badge>
                <span className="text-xs text-parchment">{t.my_characters.join(", ")}</span>
              </>
            )}
            {t.my_role && (
              <>
                <Badge tone="gold">You run this</Badge>
                <span className="text-xs text-mist">{roleLabel(t.my_role)}</span>
              </>
            )}
            {newPlayers && <Badge tone={t.new_players === "welcoming" ? "gold" : "mist"}>{newPlayers}</Badge>}
            {leadSuspended && <Badge tone="blood">lead suspended</Badge>}
          </span>
        )}
      </span>
    </Link>
  );
}

function NewTroupe() {
  const [form, setForm] = useState({ name: "", description: "", lead_handle: "" });
  const create = useAction(async () => {
    await unwrap(api.POST("/api/troupes", { body: form }));
    setForm({ name: "", description: "", lead_handle: "" });
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

/**
 * Anyone may ask the custodian for a troupe of their own, which they would lead.
 * Few players ever need it, so it is one line until opened; closing it keeps
 * what was typed.
 */
function AskForTroupe() {
  const blank = { name: "", description: "", note: "" };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const toast = useToast();
  const ask = useAction(async () => {
    await unwrap(api.POST("/api/troupe-requests", { body: form }));
    setForm(blank);
    setOpen(false);
    toast({ message: "Request sent to the custodian" });
  });
  if (!open)
    return (
      <p className="text-sm text-mist">
        Running a game of your own?{" "}
        <button type="button" className="text-gold underline hover:text-parchment" aria-expanded={false} onClick={() => setOpen(true)}>
          Ask for a new troupe
        </button>
      </p>
    );
  return (
    <Card
      title="Ask for a new troupe"
      actions={
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
      }
    >
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          ask.mutate(undefined);
        }}
      >
        <p className="text-sm text-mist">
          This is for running a game of your own; to play in a troupe, join it from your character&rsquo;s page. The custodian makes troupes. If they approve, you will be
          its lead storyteller.
        </p>
        <Field label="Troupe name">
          <Input required autoFocus maxLength={200} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
