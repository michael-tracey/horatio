import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LiveReset, PlayerSummary } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { DataTable, type Column } from "../../components/DataTable";
import { Dialog } from "../../components/Dialog";
import { LogList } from "../../components/LogList";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useWidePage } from "../../components/widePage";
import { useDates } from "../../dates";
import { memberSince } from "../players";
import { ChangeEmail, EmailChanges } from "./ChangeEmail";
import { MergeAccounts } from "./MergeAccounts";
import { PersonCharacters } from "./MoveCharacter";
import { ResetPassword, useCancelReset } from "./ResetPassword";
import { ResetTwoStep } from "./ResetTwoStep";
import { SuspendedPeople, SuspendPerson } from "./Suspension";
import { ViewAs } from "./ViewAs";
import { SectionLabel } from "../../components/Headings";

/** Every account, for the custodian: find someone by name, handle or email, or by the troupe an active character
 * of theirs is home in, open their profile, see all their characters under the
 * chevron on their row, or act on their account from the ⋯ there. Below, who is
 * suspended, the reset links out now and who has reset their password, and the
 * email changes. */
export function PeopleTab() {
  useWidePage();
  // A link can open it searched already: a new sign-up's notice names their handle (#757).
  const [params] = useSearchParams();
  const [q, setQ] = useState(() => params.get("q") ?? "");
  const [troupeId, setTroupeId] = useState("");
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const people = useQuery({
    queryKey: ["players", q, troupeId],
    queryFn: () => unwrap(api.GET("/api/players", { params: { query: { q, troupe_id: troupeId || undefined } } })),
    placeholderData: (previous) => previous,
  });

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <Input type="search" aria-label="Search people" placeholder="Name, handle or email…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-3" />
        <div className="mb-3">
          <Field label="Active character in">
            <Select value={troupeId} onChange={(e) => setTroupeId(e.target.value)}>
              <option value="">Any troupe</option>
              {troupes.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        {people.isPending ? (
          <Loading />
        ) : people.data?.length ? (
          <DataTable label="People" columns={COLUMNS} rows={people.data} rowKey={(p) => p.id} stackBelow="lg" expand={{ label: (p) => `${p.display_name}'s characters`, render: (p) => <OpenedRow person={p} /> }} />
        ) : (
          <Empty>No one matches.</Empty>
        )}
        <ErrorText error={people.error} />
      </Card>
      <SuspendedPeople />
      <PasswordResets />
      <EmailChanges />
    </div>
  );
}

/** A person's badges: suspended, a reset link out, a new email waiting. Null without any. */
function badges(person: PlayerSummary) {
  if (!person.suspended && !person.reset_expires_at && !person.email_change_to) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {person.suspended && <Badge tone="blood">Suspended</Badge>}
      {person.reset_expires_at && <Badge tone="gold">Reset link out</Badge>}
      {person.email_change_to && <Badge tone="gold">New email waiting</Badge>}
    </span>
  );
}

/** Each account's row: on a phone, the name over the handle and any badges, its chevron
 * at the start (DataTable's); its email and when they joined wait in the opened row (#911).
 * A handle or an email is cut short, never broken mid-word; the opened row has it in full.
 * The page is wider from xl (#913), so the columns are too: most show in full. */
const COLUMNS: Column<PlayerSummary>[] = [
  {
    key: "name",
    header: "Name",
    phone: "title",
    cell: (p) => (
      <Link to={`/players/${p.id}`} className="text-parchment hover:text-gold">
        {p.display_name}
      </Link>
    ),
  },
  {
    key: "handle",
    header: "Handle",
    phone: "shown",
    bare: true,
    className: "text-mist",
    cell: (p) => (
      <span className="block max-w-44 truncate xl:max-w-60">
        @{p.handle}
      </span>
    ),
    folded: (p) => (
      <span className="block truncate text-mist">
        @{p.handle}
      </span>
    ),
  },
  {
    key: "email",
    header: "Email",
    phone: "detail",
    className: "text-mist",
    cell: (p) => (
      <span className="block max-w-64 truncate xl:max-w-96">
        {p.email}
      </span>
    ),
  },
  { key: "since", header: "Member since", phone: "detail", className: "text-mist", cell: (p) => <MemberSince person={p} /> },
  { key: "status", header: "Status", phone: "shown", bare: true, cell: badges },
  { key: "actions", header: <span className="sr-only">Actions</span>, label: "Actions", phone: "always", className: "text-right", cell: (p) => <PersonActions person={p} /> },
];

function MemberSince({ person }: { person: PlayerSummary }) {
  const dates = useDates();
  return <>{memberSince(person.member_since, dates)}</>;
}

type Asked = "view" | "email" | "reset" | "two-step" | "suspend" | "merge";

/** What the custodian can do with an account, behind its ⋯, each in a dialog. */
function PersonActions({ person }: { person: PlayerSummary }) {
  const [open, setOpen] = useState<Asked | null>(null);
  const close = () => setOpen(null);
  const toast = useToast();
  const name = person.display_name;
  return (
    <>
      <ActionMenu label={`Actions for ${name}`} variant="ghost">
        <MenuGroup label="Help with the account">
          {!person.is_custodian && <MenuItem onSelect={() => setOpen("view")}>View as…</MenuItem>}
          <MenuItem onSelect={() => setOpen("email")}>Edit email…</MenuItem>
          <MenuItem onSelect={() => setOpen("reset")}>Reset password…</MenuItem>
          {person.two_step && <MenuItem onSelect={() => setOpen("two-step")}>Reset two-step sign-in…</MenuItem>}
        </MenuGroup>
        <MenuGroup label="Suspend or merge">
          <MenuItem onSelect={() => setOpen("suspend")}>{person.suspended ? "Lift suspension…" : "Suspend…"}</MenuItem>
          <MenuItem onSelect={() => setOpen("merge")}>Merge…</MenuItem>
        </MenuGroup>
      </ActionMenu>
      {/* The dialogs sit here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
      <ViewAs person={person} open={open === "view"} onClose={close} />
      <Dialog title={`Edit ${name}'s email`} open={open === "email"} onClose={close}>
        <ChangeEmail person={person} />
      </Dialog>
      <Dialog title={`Reset ${name}'s password`} open={open === "reset"} onClose={close}>
        <ResetPassword player={person} />
      </Dialog>
      <Dialog title={`Reset ${name}'s two-step sign-in`} open={open === "two-step"} onClose={close}>
        <ResetTwoStep
          person={person}
          onDone={() => {
            toast({ message: `${name}'s password alone signs them in now.` });
            close();
          }}
        />
      </Dialog>
      <Dialog title={person.suspended ? `Lift ${name}'s suspension` : `Suspend ${name}`} open={open === "suspend"} onClose={close}>
        <SuspendPerson
          person={person}
          onDone={() => {
            toast({ message: person.suspended ? `${name} can sign in again.` : `${name} is suspended.` });
            close();
          }}
        />
      </Dialog>
      <Dialog title={`Merge ${name} with another account`} open={open === "merge"} onClose={close}>
        <MergeAccounts person={person} onDone={close} />
      </Dialog>
    </>
  );
}

/** The row a person's chevron opens (#890): their handle, email and when they joined in
 * full, and all their characters. Under the name on a wide screen; the whole width of
 * the card on a phone. */
function OpenedRow({ person }: { person: PlayerSummary }) {
  const dates = useDates();
  return (
    <>
      <dl className="mb-2 grid gap-x-3 text-xs sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-y-0.5">
        <dt className="text-mist">Handle</dt>
        <dd className="wrap-anywhere">@{person.handle}</dd>
        <dt className="text-mist">Email</dt>
        <dd className="wrap-anywhere">{person.email}</dd>
        <dt className="text-mist">Member since</dt>
        <dd>{memberSince(person.member_since, dates)}</dd>
      </dl>
      <section aria-label={`${person.display_name}'s characters`}>
        <PersonCharacters playerId={person.id} />
      </section>
    </>
  );
}

/** The reset links that work now, and the log of links made, emailed, asked for
 * and used. */
function PasswordResets() {
  const resets = useQuery({ queryKey: ["password-resets"], queryFn: () => unwrap(api.GET("/api/password-resets")) });
  return (
    <Card title="Password resets">
      {resets.isPending ? (
        <Loading />
      ) : resets.data ? (
        <div className="flex flex-col gap-4">
          <section>
            <SectionLabel className="mb-1">Links that work now</SectionLabel>
            {resets.data.live.length ? (
              <ul className="divide-y divide-ash/50 text-sm">
                {resets.data.live.map((r) => (
                  <LiveLink key={r.user_id} reset={r} />
                ))}
              </ul>
            ) : (
              <Empty>No one has a reset link out.</Empty>
            )}
          </section>
          <section>
            <SectionLabel className="mb-1">Recently</SectionLabel>
            {resets.data.log.length ? (
              <LogList entries={resets.data.log} linkTo={(e) => (typeof e.data.user_id === "string" ? `/players/${e.data.user_id}` : null)} />
            ) : (
              <Empty>No one has reset a password yet.</Empty>
            )}
          </section>
        </div>
      ) : null}
      <ErrorText error={resets.error} />
    </Card>
  );
}

function LiveLink({ reset }: { reset: LiveReset }) {
  const cancel = useCancelReset(reset.user_id);
  const dates = useDates();
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
      <span>
        <Link to={`/players/${reset.user_id}`} className="hover:text-gold">
          {reset.display_name}
        </Link>{" "}
        <span className="text-xs text-mist">
          until {dates.dateTime(reset.expires_at)}, {reset.asked_themselves ? "asked for by them" : `made by ${reset.made_by}`}
        </span>
      </span>
      <Button
        type="button"
        variant="ghost"
        className="min-h-8 px-2 text-xs"
        aria-label={`Cancel ${reset.display_name}'s reset link`}
        disabled={cancel.isPending}
        onClick={() => cancel.mutate(undefined)}
      >
        Cancel
      </Button>
      <ErrorText error={cancel.error} />
    </li>
  );
}
