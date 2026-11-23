import { browserSupportsWebAuthn, startAuthentication } from "@simplewebauthn/browser";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, CUSTODIAN_ACCESS_NEEDED, unwrap } from "../api/client";
import { useCustodianAccess } from "../custodianAccess";
import { useDates } from "../dates";
import { useAction, useMe } from "../hooks";
import { passkeyProblem } from "../passkeys";
import { Dialog } from "./Dialog";
import { Button, ErrorText, Field, Input, Textarea } from "./ui";

// After the custodian puts the offer away, another refusal doesn't offer it again for a while.
const QUIET_FOR_MS = 30_000;

/** Round every page, for the custodian (#1213): while custodian access is on, a banner
 * saying so, with Switch off; and, when something they did needed it, the offer to
 * switch it on. Every page is asked again as it goes on or off. */
export function CustodianAccess() {
  const me = useMe();
  const access = useCustodianAccess();
  const client = useQueryClient();
  const dates = useDates();
  const [offered, setOffered] = useState(false);
  const putAway = useRef(0);
  const on = !!access.data?.on;
  const endsAt = access.data?.ends_at;

  // On or off, what every page shows changes with it.
  const was = useRef<boolean | null>(null);
  useEffect(() => {
    if (access.data === undefined) return;
    if (was.current !== null && was.current !== on) void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "custodian-access" });
    was.current = on;
  }, [access.data, on, client]);

  // Asked again when it would end, as using it may have moved the end on.
  useEffect(() => {
    if (!endsAt) return;
    const timer = window.setTimeout(() => void access.refetch(), Math.max(new Date(endsAt).getTime() - Date.now(), 0) + 1000);
    return () => window.clearTimeout(timer);
  }, [endsAt, access]);

  useEffect(() => {
    if (!me.data?.is_custodian) return;
    const offer = () => {
      if (Date.now() - putAway.current > QUIET_FOR_MS) setOffered(true);
    };
    window.addEventListener(CUSTODIAN_ACCESS_NEEDED, offer);
    return () => window.removeEventListener(CUSTODIAN_ACCESS_NEEDED, offer);
  }, [me.data?.is_custodian]);

  const off = useAction(async () => {
    await unwrap(api.POST("/api/custodian-access/stop"));
  });

  if (!me.data?.is_custodian) return null;
  return (
    <>
      {on && access.data && (
        <div role="status" aria-label="Custodian access" className="border-b border-blood/60 bg-blood/20 text-sm print:hidden">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-2">
            <p>
              <strong>Custodian access is on.</strong> <span className="text-mist">{access.data.reason}</span>{" "}
              {endsAt && <span className="text-mist">Until {dates.time(endsAt)}, or an hour after you last use it.</span>}
            </p>
            <button type="button" className="rounded-md border border-blood/60 px-3 py-1 hover:bg-blood/20" disabled={off.isPending} onClick={() => off.mutate(undefined)}>
              Switch off
            </button>
          </div>
        </div>
      )}
      <Dialog
        title="Switch on custodian access"
        open={offered && !on}
        onClose={() => {
          putAway.current = Date.now();
          setOffered(false);
        }}
      >
        <p className="mb-3 text-sm text-mist">That needs custodian access. Until you switch it on, you see Horatio as your troupe roles make you.</p>
        <SwitchOn onDone={() => setOffered(false)} />
      </Dialog>
    </>
  );
}

/** Switching custodian access on: a reason, and their second step again (their
 * password, with none set up). For an hour from its last use. */
export function SwitchOn({ onDone }: { onDone?: () => void }) {
  const access = useCustodianAccess();
  const [reason, setReason] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [recovery, setRecovery] = useState(false);
  const ways = access.data?.second_step ?? [];
  const withPasskey = !recovery && ways.includes("passkey") && browserSupportsWebAuthn();
  const withCode = recovery || ways.includes("app") || (ways.includes("passkey") && !browserSupportsWebAuthn());
  const withPassword = ways.length === 0;

  const give = useAction(async () => {
    await unwrap(api.POST("/api/custodian-access", { body: withPassword ? { reason, password } : { reason, code } }));
    onDone?.();
  });
  const passkey = useAction(async () => {
    const optionsJSON = await unwrap(api.POST("/api/custodian-access/passkey/options"));
    let credential;
    try {
      credential = await startAuthentication({ optionsJSON: optionsJSON as never });
    } catch (error) {
      throw passkeyProblem(error);
    }
    await unwrap(api.POST("/api/custodian-access", { body: { reason, credential: credential as never } }));
    onDone?.();
  });

  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        give.mutate(undefined);
      }}
    >
      <p className="text-mist">
        It lasts an hour from the last thing you do with it, and goes in the audit log with your reason. If you open what only staff see in a troupe you play in, its lead
        storyteller is told, with your reason.
      </p>
      <Field label="Reason">
        <Textarea rows={2} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="A player asked for help with their sheet" />
      </Field>
      {withPasskey && (
        <>
          <Button type="button" disabled={passkey.isPending || !reason.trim()} onClick={() => passkey.mutate(undefined)} className="self-start">
            Switch on with a passkey
          </Button>
          <ErrorText error={passkey.error} />
        </>
      )}
      {withCode && (
        <Field label={recovery ? "Recovery code" : "Code from your app"}>
          <Input
            required
            autoComplete="one-time-code"
            autoCapitalize="none"
            spellCheck={false}
            inputMode={recovery ? "text" : "numeric"}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </Field>
      )}
      {withPassword && (
        <Field label="Your password">
          <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
      )}
      {(withCode || withPassword) && (
        <>
          <ErrorText error={give.error} />
          <Button type="submit" variant={withPasskey ? "secondary" : "primary"} disabled={give.isPending || !reason.trim()} className="self-start">
            Switch on
          </Button>
        </>
      )}
      {(ways.includes("app") || ways.includes("passkey")) && ways.includes("recovery_code") && (
        <button
          type="button"
          className="self-start text-gold underline"
          onClick={() => {
            setRecovery(!recovery);
            setCode("");
          }}
        >
          {recovery ? (ways.includes("app") ? "Use your authenticator app instead" : "Use your passkey instead") : "Use a recovery code instead"}
        </button>
      )}
    </form>
  );
}
