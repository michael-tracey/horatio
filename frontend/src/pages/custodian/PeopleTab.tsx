import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LiveReset, PlayerSummary } from "../../api/types";
import { LogList } from "../../components/LogList";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { memberSince } from "../players";
import { ResetPassword, useCancelReset } from "./ResetPassword";
import { SuspendedPeople, SuspendPerson } from "./Suspension";

/** Every account, for the custodian: find someone by name, handle or email, or by the troupe an active character
 * of theirs is home in, open their
 * profile, or reset their password here. Below, the reset links out now and who
 * has reset their password. */
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
          <ul className="divide-y divide-ash text-sm">
            {people.data.map((p) => (
              <Person key={p.id} person={p} />
            ))}
          </ul>
        ) : (
          <Empty>No one matches.</Empty>
        )}
        <ErrorText error={people.error} />
      </Card>
      <SuspendedPeople />
      <PasswordResets />
    </div>
  );
}

function Person({ person }: { person: PlayerSummary }) {
  const [open, setOpen] = useState<"reset" | "suspend" | null>(null);
  const dates = useDates();
  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <Link to={`/players/${person.id}`} className="flex min-w-0 flex-col gap-0.5 hover:text-gold sm:flex-row sm:items-center sm:gap-3">
          <span>{person.display_name}</span>
          <span className="text-xs break-all text-mist">
            @{person.handle} · {person.email} · since {memberSince(person.member_since, dates)}
          </span>
        </Link>
        <span className="flex items-center gap-2">
          {person.suspended && <Badge tone="blood">suspended</Badge>}
          {person.reset_expires_at && <Badge tone="gold">reset link out</Badge>}
          <Button
            type="button"
            variant="ghost"
            className="min-h-8 px-2 text-xs"
            aria-expanded={open === "reset"}
            aria-label={`Reset password for ${person.display_name}`}
            onClick={() => setOpen(open === "reset" ? null : "reset")}
          >
            Reset password
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="min-h-8 px-2 text-xs"
            aria-expanded={open === "suspend"}
            aria-label={`${person.suspended ? "Lift the suspension of" : "Suspend"} ${person.display_name}`}
            onClick={() => setOpen(open === "suspend" ? null : "suspend")}
          >
            {person.suspended ? "Lift suspension" : "Suspend"}
          </Button>
        </span>
      </div>
      {open && (
        <div className="mt-2 rounded-md border border-ash bg-night/40 p-3">
          {open === "reset" ? <ResetPassword player={person} /> : <SuspendPerson person={person} />}
        </div>
      )}
    </li>
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
