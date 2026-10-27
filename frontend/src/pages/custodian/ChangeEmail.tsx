import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { EmailChangeOut, PendingEmailFor } from "../../api/types";
import { LogList } from "../../components/LogList";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { useCanEmail } from "./ResetPassword";

/** Send the link for someone's email change again (a new one, good for another 7 days), or cancel the change. */
export function useEmailChangeActions(userId: string, onDone: (sent: EmailChangeOut | null) => void) {
  const path = { params: { path: { user_id: userId } } };
  const resend = useAction(async () => onDone(await unwrap(api.POST("/api/players/{user_id}/email-change/resend", path))));
  const cancel = useAction(async () => {
    await unwrap(api.DELETE("/api/players/{user_id}/email-change", path));
    onDone(null);
  });
  return { resend, cancel };
}

/** Where the link went, or the link itself to send on when Horatio couldn't email it. */
export function SentLink({ sent }: { sent: EmailChangeOut }) {
  const [copied, setCopied] = useState(false);
  return (
    <>
      {sent.emailed_to && <Notice>The link to confirm it is on its way to {sent.emailed_to}.</Notice>}
      {sent.email_error && <ErrorText error={`It could not be emailed: ${sent.email_error}`} />}
      {sent.url && (
        <>
          <p className="text-mist">Send this link to {sent.new_email} yourself. It works once, for 7 days.</p>
          <Input readOnly aria-label="Link to confirm the new email" value={sent.url} onFocus={(e) => e.target.select()} />
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(sent.url ?? "").then(() => setCopied(true));
            }}
          >
            {copied ? "Copied" : "Copy link"}
          </Button>
        </>
      )}
    </>
  );
}

type Person = { id: string; display_name: string; email: string };

/**
 * The custodian changes someone's email, for a player who has lost their old
 * address: with a reason, and only once the link sent to the new address is
 * opened. Used in the Custodian menu's People list.
 */
export function ChangeEmail({ person }: { person: Person }) {
  const canEmail = useCanEmail();
  const dates = useDates();
  const [address, setAddress] = useState("");
  const [reason, setReason] = useState("");
  const [sent, setSent] = useState<EmailChangeOut | null>(null);
  const profile = useQuery({
    queryKey: ["player", person.id],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: person.id } } })),
  });
  const start = useAction(async () => {
    setSent(await unwrap(api.POST("/api/players/{user_id}/email-change", { params: { path: { user_id: person.id } }, body: { email: address, reason } })));
    setAddress("");
    setReason("");
  });
  const { resend, cancel } = useEmailChangeActions(person.id, setSent);
  const waiting = profile.data?.email_change;

  if (profile.isPending) return <Loading />;
  return (
    <div className="flex flex-col gap-3 text-sm">
      {waiting ? (
        <>
          <p>
            Waiting for {person.display_name} to confirm {waiting.new_email}, until {dates.dateTime(waiting.expires_at)}.{" "}
            <span className="text-mist">{waiting.asked_themselves ? "They asked for it themselves." : `Started by ${waiting.made_by}.`}</span>
          </p>
          {sent && <SentLink sent={sent} />}
          <ErrorText error={resend.error ?? cancel.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" disabled={resend.isPending} onClick={() => resend.mutate(undefined)}>
              {canEmail ? "Send the link again" : "Make a new link"}
            </Button>
            <Button type="button" variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined)}>
              Cancel the change
            </Button>
          </div>
        </>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            start.mutate(undefined);
          }}
        >
          <p className="text-mist">
            {person.display_name} keeps {person.email} until they open the link sent to the new address, within 7 days; then the old address is told.{" "}
            {!canEmail && "Horatio can't send email here, so you'll get the link to send them yourself."}
          </p>
          <Field label="New email">
            <Input type="email" required autoComplete="off" value={address} onChange={(e) => setAddress(e.target.value)} />
          </Field>
          <Field label="Reason" hint="For the log. They aren't shown it.">
            <Textarea rows={2} required maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          {sent === null && cancel.isSuccess && <Notice>Cancelled. Their email stays as it is.</Notice>}
          <ErrorText error={start.error ?? profile.error} />
          <Button type="submit" variant="secondary" disabled={start.isPending} className="self-start">
            Change email
          </Button>
        </form>
      )}
    </div>
  );
}

/** The email changes waiting to be confirmed, and the log of changes started, confirmed and cancelled, with both addresses. */
export function EmailChanges() {
  const changes = useQuery({ queryKey: ["email-changes"], queryFn: () => unwrap(api.GET("/api/email-changes")) });
  return (
    <Card title="Email changes">
      {changes.isPending ? (
        <Loading />
      ) : changes.data ? (
        <div className="flex flex-col gap-4">
          <section>
            <h3 className="mb-1 text-sm text-mist">Waiting to be confirmed</h3>
            {changes.data.pending.length ? (
              <ul className="divide-y divide-ash/50 text-sm">
                {changes.data.pending.map((c) => (
                  <Waiting key={c.user_id} change={c} />
                ))}
              </ul>
            ) : (
              <Empty>No email change is waiting.</Empty>
            )}
          </section>
          <section>
            <h3 className="mb-1 text-sm text-mist">Recently</h3>
            {changes.data.log.length ? (
              <LogList entries={changes.data.log} linkTo={(e) => (typeof e.data.user_id === "string" ? `/players/${e.data.user_id}` : null)} />
            ) : (
              <Empty>No one has changed an email yet.</Empty>
            )}
          </section>
        </div>
      ) : null}
      <ErrorText error={changes.error} />
    </Card>
  );
}

function Waiting({ change }: { change: PendingEmailFor }) {
  const dates = useDates();
  const { cancel } = useEmailChangeActions(change.user_id, () => {});
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
      <span>
        <Link to={`/players/${change.user_id}`} className="hover:text-gold">
          {change.display_name}
        </Link>{" "}
        <span className="text-xs break-all text-mist">
          {change.email} → {change.new_email}, until {dates.dateTime(change.expires_at)}, {change.asked_themselves ? "asked for by them" : `started by ${change.made_by}`}
        </span>
      </span>
      <Button
        type="button"
        variant="ghost"
        className="min-h-8 px-2 text-xs"
        aria-label={`Cancel ${change.display_name}'s email change`}
        disabled={cancel.isPending}
        onClick={() => cancel.mutate(undefined)}
      >
        Cancel
      </Button>
      <ErrorText error={cancel.error} />
    </li>
  );
}
