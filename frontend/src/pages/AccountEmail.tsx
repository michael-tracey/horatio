import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { EmailChangeOut, PlayerOut } from "../api/types";
import { Button, Card, ErrorText, Field, Input, Notice } from "../components/ui";
import { useDates } from "../dates";
import { useAction } from "../hooks";
import { SentLink, useEmailChangeActions } from "./custodian/ChangeEmail";
import { useCanEmail } from "./custodian/ResetPassword";

/**
 * The signed-in player's email, and changing it: they give their password, and
 * it changes only when they open the link sent to the new address. Without
 * email on the server, the custodian changes it for them.
 */
export function AccountEmail({ player }: { player: PlayerOut }) {
  const canEmail = useCanEmail();
  const dates = useDates();
  const [open, setOpen] = useState(false);
  const [address, setAddress] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState<EmailChangeOut | null>(null);
  const start = useAction(async () => {
    setSent(await unwrap(api.POST("/api/players/{user_id}/email-change", { params: { path: { user_id: player.id } }, body: { email: address, password } })));
    setOpen(false);
    setAddress("");
    setPassword("");
  });
  const { resend, cancel } = useEmailChangeActions(player.id, setSent);
  const waiting = player.email_change;

  return (
    <Card title="Email">
      <div className="flex flex-col gap-3 text-sm">
        <p>
          You sign in with {player.email}, and Horatio's emails go there. <span className="text-mist">Only you and the custodian see it.</span>
        </p>
        {waiting ? (
          <>
            <p>
              {waiting.asked_themselves ? "You're changing it" : `${waiting.made_by}, the custodian, is changing it`} to {waiting.new_email}. Open the link sent there by{" "}
              {dates.dateTime(waiting.expires_at)} to confirm it; until then, nothing changes.
            </p>
            {sent && <SentLink sent={sent} />}
            <ErrorText error={resend.error ?? cancel.error} />
            <div className="flex flex-wrap gap-2">
              {canEmail && (
                <Button type="button" variant="secondary" disabled={resend.isPending} onClick={() => resend.mutate(undefined)}>
                  Send the link again
                </Button>
              )}
              <Button type="button" variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined)}>
                Cancel the change
              </Button>
            </div>
          </>
        ) : !canEmail ? (
          <p className="text-mist">Horatio can't send email here, so ask the custodian to change your email.</p>
        ) : open ? (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate(undefined);
            }}
          >
            <p className="text-mist">Horatio will email a link to the new address. Your email changes when you open it, within 7 days, and your old address is told.</p>
            <Field label="New email">
              <Input type="email" required autoComplete="email" value={address} onChange={(e) => setAddress(e.target.value)} />
            </Field>
            <Field label="Your password">
              <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <ErrorText error={start.error} />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="secondary" disabled={start.isPending}>
                Send the link
              </Button>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                Never mind
              </Button>
            </div>
          </form>
        ) : (
          <>
            {cancel.isSuccess && <Notice>Cancelled. Your email stays as it is.</Notice>}
            <Button type="button" variant="secondary" className="self-start" onClick={() => setOpen(true)}>
              Change email
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}
