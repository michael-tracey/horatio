import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { ResetLink } from "../../api/types";
import { Button, ErrorText, Input, Notice } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/** Whether Horatio can send email here: if not, reset links are copied and sent by hand. */
export function useCanEmail() {
  const help = useQuery({ queryKey: ["forgot"], queryFn: () => unwrap(api.GET("/api/auth/forgot")), staleTime: 5 * 60_000 });
  return help.data?.can_email ?? false;
}

type Person = { id: string; display_name: string; email?: string | null; reset_expires_at: string | null };

/** Cancel someone's live reset link, so it no longer works. */
export function useCancelReset(userId: string, onDone?: () => void) {
  return useAction(async () => {
    await unwrap(api.DELETE("/api/players/{user_id}/password-reset", { params: { path: { user_id: userId } } }));
    onDone?.();
  });
}

/**
 * The custodian's reset link for someone locked out: whether one is live, and a
 * new one to copy or have Horatio email. Used on the person's page and in the
 * Custodian menu's People list.
 */
export function ResetPassword({ player }: { player: Person }) {
  const canEmail = useCanEmail();
  const dates = useDates();
  const [link, setLink] = useState<ResetLink | null>(null);
  const [copied, setCopied] = useState(false);
  const make = useAction(async (email: boolean) => {
    setLink(await unwrap(api.POST("/api/players/{user_id}/password-reset", { params: { path: { user_id: player.id } }, body: { email } })));
    setCopied(false);
  });
  const cancel = useCancelReset(player.id, () => setLink(null));
  const copy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link.url);
    setCopied(true);
  };
  const live = link?.expires_at ?? player.reset_expires_at;

  return (
    <div className="flex flex-col gap-3 text-sm">
      {live ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p>
            {player.display_name} has a reset link, unused, until {dates.dateTime(live)}.
          </p>
          <Button type="button" variant="ghost" className="min-h-8 px-2" disabled={cancel.isPending} onClick={() => cancel.mutate(undefined)}>
            Cancel link
          </Button>
        </div>
      ) : (
        <p className="text-mist">
          Make a link that lets {player.display_name} set a new password. It works once, for a day, and replaces any earlier link.{" "}
          {canEmail ? `Horatio can email it to ${player.email ?? "them"}, or you can send it yourself.` : "Send it to them yourself."}
        </p>
      )}
      {link && (
        <>
          {link.emailed_to && <Notice>Emailed to {link.emailed_to}. You can copy it too.</Notice>}
          {link.email_error && <ErrorText error={`It could not be emailed: ${link.email_error} Copy it and send it yourself.`} />}
          <Input readOnly aria-label="Reset link" value={link.url} onFocus={(e) => e.target.select()} />
          <Button type="button" variant="secondary" onClick={() => void copy()}>
            {copied ? "Copied" : "Copy link"}
          </Button>
        </>
      )}
      <ErrorText error={make.error ?? cancel.error} />
      <div className="flex flex-wrap gap-2">
        {canEmail && (
          <Button type="button" variant={link ? "ghost" : "secondary"} disabled={make.isPending} onClick={() => make.mutate(true)}>
            {live ? "Email a new link" : "Email a reset link"}
          </Button>
        )}
        <Button type="button" variant={link || canEmail ? "ghost" : "secondary"} disabled={make.isPending} onClick={() => make.mutate(false)}>
          {live ? "Make a new link" : canEmail ? "Make a link to copy" : "Make a reset link"}
        </Button>
      </div>
    </div>
  );
}
