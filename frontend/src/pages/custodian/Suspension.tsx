import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { Suspended } from "../../api/types";
import { LogList } from "../../components/LogList";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/** Who is suspended now, and the log of suspensions: for the custodian only. */
export function useSuspensions(enabled = true) {
  return useQuery({ queryKey: ["suspensions"], queryFn: () => unwrap(api.GET("/api/suspensions")), enabled });
}

/** The ids of everyone suspended now, for marks on other pages: the custodian's only. */
export function useSuspendedIds(enabled: boolean): Set<string> {
  const suspensions = useSuspensions(enabled);
  return new Set(suspensions.data?.suspended.map((s) => s.user_id));
}

type Person = { id: string; display_name: string; suspended?: boolean };

/**
 * Suspend someone, with a reason only the custodian sees and an end date if it
 * has one; or lift their suspension, with a reason too. Used in the Custodian
 * menu's People list.
 */
export function SuspendPerson({ person }: { person: Person }) {
  const dates = useDates();
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const suspend = useAction(async () => {
    const done = await unwrap(
      api.POST("/api/players/{user_id}/suspension", {
        params: { path: { user_id: person.id } },
        body: { reason, ends_at: until ? dates.fromInput(until).toISOString() : null },
      }),
    );
    setEmailError(done.email_error ?? null);
    setReason("");
    setUntil("");
  });
  const lift = useAction(async () => {
    const done = await unwrap(api.POST("/api/players/{user_id}/suspension/lift", { params: { path: { user_id: person.id } }, body: { reason } }));
    setEmailError(done.email_error ?? null);
    setReason("");
  });
  const action = person.suspended ? lift : suspend;

  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        action.mutate(undefined);
      }}
    >
      <p className="text-mist">
        {person.suspended
          ? `Lifting the suspension lets ${person.display_name} sign in again, and they are emailed to say so.`
          : `${person.display_name} is signed out everywhere at once, and can't sign in until you lift it or the end date passes. Their characters stay as they are, but take no new actions. They are emailed, without the reason.`}
      </p>
      <Field label={person.suspended ? "Why lift it" : "Reason"} hint={person.suspended ? "For the log." : "Only the custodian sees it."}>
        <Textarea required rows={2} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      {!person.suspended && (
        <Field label="Until" hint={`Optional: leave it empty to lift it by hand. Times are in ${dates.zone.replace(/_/g, " ")}.`}>
          <Input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
        </Field>
      )}
      {emailError && <ErrorText error={`They could not be emailed: ${emailError}`} />}
      <ErrorText error={action.error} />
      <Button type="submit" variant={person.suspended ? "secondary" : "danger"} disabled={action.isPending || !reason.trim()} className="self-start">
        {person.suspended ? "Lift suspension" : `Suspend ${person.display_name}`}
      </Button>
    </form>
  );
}

/** Who is suspended now, the troupes they lead (which want a new lead), and the log. */
export function SuspendedPeople() {
  const suspensions = useSuspensions();
  return (
    <Card title="Suspended">
      {suspensions.isPending ? (
        <Loading />
      ) : suspensions.data ? (
        <div className="flex flex-col gap-4">
          {suspensions.data.suspended.length ? (
            <ul className="divide-y divide-ash/50 text-sm" aria-label="Suspended people">
              {suspensions.data.suspended.map((s) => (
                <SuspendedPerson key={s.user_id} suspended={s} />
              ))}
            </ul>
          ) : (
            <Empty>No one is suspended.</Empty>
          )}
          {suspensions.data.log.length > 0 && (
            <section>
              <h3 className="mb-1 text-sm text-mist">Recently</h3>
              <LogList entries={suspensions.data.log} linkTo={(e) => (typeof e.data.user_id === "string" ? `/players/${e.data.user_id}` : null)} />
            </section>
          )}
        </div>
      ) : null}
      <ErrorText error={suspensions.error} />
    </Card>
  );
}

function SuspendedPerson({ suspended: s }: { suspended: Suspended }) {
  const dates = useDates();
  return (
    <li className="flex flex-col gap-1 py-2">
      <span>
        <Link to={`/players/${s.user_id}`} className="hover:text-gold">
          {s.display_name}
        </Link>{" "}
        <span className="text-xs text-mist">
          @{s.handle} · since {dates.dateTime(s.since)} by {s.suspended_by}, {s.ends_at ? `until ${dates.dateTime(s.ends_at)}` : "until lifted"}
        </span>
      </span>
      <span className="text-xs text-parchment/80">“{s.reason}”</span>
      {s.leads.length > 0 && (
        <Notice>
          Leads{" "}
          {s.leads.map((t, i) => (
            <span key={t.id}>
              {i > 0 && ", "}
              <Link to={`/troupes/${t.id}/staff`} className="text-gold underline">
                {t.name}
              </Link>
            </span>
          ))}
          : appoint a new lead storyteller while they are away.
        </Notice>
      )}
    </li>
  );
}
