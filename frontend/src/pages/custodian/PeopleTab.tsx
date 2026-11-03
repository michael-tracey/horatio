import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LiveReset, PlayerSummary } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { LogList } from "../../components/LogList";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { memberSince } from "../players";
import { ChangeEmail, EmailChanges } from "./ChangeEmail";
import { MergeAccounts } from "./MergeAccounts";
import { PersonCharacters } from "./MoveCharacter";
import { ResetPassword, useCancelReset } from "./ResetPassword";
import { SuspendedPeople, SuspendPerson } from "./Suspension";
import { ViewAs } from "./ViewAs";

/** Every account, for the custodian: find someone by name, handle or email, or by the troupe an active character
 * of theirs is home in, open their profile, or act on their account from the ⋯ on
 * their row. Below, who is suspended, the reset links out now and who has reset
 * their password, and the email changes. */
export function PeopleTab() {
  const [q, setQ] = useState("");
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
          <table aria-label="People" className="w-full text-sm">
            {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
            <thead className="max-lg:sr-only">
              <tr className="border-b border-ash text-left text-xs text-mist">
                <th className="py-2 pr-3 font-normal">Name</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Handle</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Email</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Member since</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Status</th>
                <th className="py-2 font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {people.data.map((p) => (
                <Person key={p.id} person={p} />
              ))}
            </tbody>
          </table>
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

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

type Opened = "view" | "characters" | "email" | "reset" | "suspend" | "merge";

/** One account: its details, and what the custodian can do with it behind ⋯, each in a dialog. */
function Person({ person }: { person: PlayerSummary }) {
  const [open, setOpen] = useState<Opened | null>(null);
  const close = () => setOpen(null);
  const toast = useToast();
  const dates = useDates();
  const name = person.display_name;
  const since = memberSince(person.member_since, dates);
  const badges = (
    <>
      {person.suspended && <Badge tone="blood">Suspended</Badge>}
      {person.reset_expires_at && <Badge tone="gold">Reset link out</Badge>}
      {person.email_change_to && <Badge tone="gold">New email waiting</Badge>}
    </>
  );
  return (
    <tr>
      <td className="py-2.5 pr-3 align-top">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Link to={`/players/${person.id}`} className="text-parchment hover:text-gold">
            {name}
          </Link>
          <span className="flex flex-wrap gap-1 lg:hidden">{badges}</span>
        </span>
        <span className="mt-0.5 block text-xs text-mist wrap-anywhere lg:hidden">
          @{person.handle} · {person.email} · since {since}
        </span>
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist wrap-anywhere`}>@{person.handle}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist wrap-anywhere`}>{person.email}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{since}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>
        <span className="flex flex-wrap gap-1">{badges}</span>
      </td>
      <td className="w-px py-1 text-right align-top">
        <ActionMenu label={`Actions for ${name}`} variant="ghost">
          <MenuGroup label="Help with the account">
            {!person.is_custodian && <MenuItem onSelect={() => setOpen("view")}>View as…</MenuItem>}
            <MenuItem onSelect={() => setOpen("characters")}>Characters</MenuItem>
            <MenuItem onSelect={() => setOpen("email")}>Change email…</MenuItem>
            <MenuItem onSelect={() => setOpen("reset")}>Reset password…</MenuItem>
          </MenuGroup>
          <MenuGroup label="Suspend or merge">
            <MenuItem onSelect={() => setOpen("suspend")}>{person.suspended ? "Lift suspension…" : "Suspend…"}</MenuItem>
            <MenuItem onSelect={() => setOpen("merge")}>Merge…</MenuItem>
          </MenuGroup>
        </ActionMenu>
        {/* The dialogs sit here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
        <ViewAs person={person} open={open === "view"} onClose={close} />
        <Dialog title={`${name}'s characters`} open={open === "characters"} onClose={close}>
          <PersonCharacters playerId={person.id} />
        </Dialog>
        <Dialog title={`Change ${name}'s email`} open={open === "email"} onClose={close}>
          <ChangeEmail person={person} />
        </Dialog>
        <Dialog title={`Reset ${name}'s password`} open={open === "reset"} onClose={close}>
          <ResetPassword player={person} />
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
      </td>
    </tr>
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
            <h3 className="mb-1 text-sm text-mist">Links that work now</h3>
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
            <h3 className="mb-1 text-sm text-mist">Recently</h3>
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
