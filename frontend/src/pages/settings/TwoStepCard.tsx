import { useQuery } from "@tanstack/react-query";
import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { SectionLabel } from "../../components/Headings";
import { QrCode } from "../../components/QrCode";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Field, Input, Loaded, Notice } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction, useMe } from "../../hooks";
import { replaceProblem } from "../../passkeys";

type AppSetup = components["schemas"]["AppSetup"];
type TwoStep = components["schemas"]["TwoStepOut"];

const TWO_STEP = ["two-step"];

/** The secret as an app wants it typed: in fours, "ABCD EFGH ...". */
export function spaced(secret: string): string {
  return secret.replace(/(.{4})(?=.)/g, "$1 ");
}

/** What a passkey that may not sign in alone, with no password, says of itself (#1098):
 * null for one that can. Those added before passkeys could sign in alone never said.
 * Each that may not can be replaced with one that does (#1110). */
export function aloneNote(discoverable: boolean | null): string | null {
  if (discoverable === true) return null;
  if (discoverable === false) return "Signs you in only after your password: the device that keeps it can't sign you in with it alone.";
  return "May not sign you in alone, without your password: it was added before passkeys could. To be sure, replace it on the device that keeps it.";
}

/** What asks for the password again: turning off the app, new codes, removing or
 * replacing a passkey. Adding one asks for it in its own form. */
type Asking = { what: "app" } | { what: "codes" } | { what: "passkey" | "replace"; id: string; name: string };

/**
 * Two-step sign-in (#1057): after the password, a passkey on the person's phone or
 * computer, or a code from an authenticator app, with one-time recovery codes for
 * when both are lost. A passkey is made by the browser; an app is set up with a QR
 * code (and the key, to type in), then a code from it. The recovery codes come once,
 * with the first second step. Adding, replacing or removing a passkey, turning off the
 * app, or making new recovery codes, asks for the password again, before the browser
 * is asked for anything (#1110). Someone who must have it can't remove their last. A
 * passkey that may not sign in alone is replaced in one go: the new one is made and
 * kept before the old one goes, so a cancelled or failed try leaves the old one as it was.
 */
export function TwoStepCard({ onDone }: { onDone?: () => void }) {
  const toast = useToast();
  const dates = useDates();
  const state = useQuery({ queryKey: TWO_STEP, queryFn: () => unwrap(api.GET("/api/two-step")) });
  const [setup, setSetup] = useState<AppSetup | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [addingPassword, setAddingPassword] = useState("");

  /** A second step is on: the recovery codes, if they came with it, then on. */
  const turnedOn = (made: string[], message: string) => {
    toast({ message });
    if (made.length) setCodes(made);
    else onDone?.();
  };
  const addPasskey = useAction(async () => {
    const optionsJSON = await unwrap(api.POST("/api/two-step/passkeys/options", { body: { password: addingPassword } }));
    setAddingPassword("");
    // The browser asks the person to make it, with their face, finger or PIN.
    const credential = await startRegistration({ optionsJSON: optionsJSON as never });
    const made = await unwrap(api.POST("/api/two-step/passkeys", { body: { credential: credential as never, name: name.trim() || "Passkey" } }));
    setName("");
    turnedOn(made.recovery_codes, "Passkey added.");
  }, [TWO_STEP, ["me"]]);
  const replacePasskey = useAction(
    async (old: { id: string; name: string }) => {
      const path = { passkey_id: old.id };
      try {
        const optionsJSON = await unwrap(api.POST("/api/two-step/passkeys/{passkey_id}/replace/options", { params: { path }, body: { password } }));
        setPassword("");
        const credential = await startRegistration({ optionsJSON: optionsJSON as never });
        await unwrap(api.POST("/api/two-step/passkeys/{passkey_id}/replace", { params: { path }, body: { credential: credential as never } }));
      } catch (error) {
        throw replaceProblem(error, old.name);
      }
      setAsking(null);
      toast({ message: `${old.name} replaced. It signs you in alone now, with no password.` });
    },
    [TWO_STEP],
  );
  const start = useAction(async () => {
    setSetup(await unwrap(api.POST("/api/two-step/app")));
    setCode("");
  }, [TWO_STEP]);
  const confirm = useAction(async () => {
    const made = await unwrap(api.POST("/api/two-step/app/confirm", { body: { code } }));
    setSetup(null);
    setCode("");
    turnedOn(made.recovery_codes, "Authenticator app turned on.");
  }, [TWO_STEP, ["me"]]);
  const withPassword = useAction(
    async (asked: Asking) => {
      const body = { password };
      if (asked.what === "codes") setCodes((await unwrap(api.POST("/api/two-step/recovery-codes", { body }))).recovery_codes);
      else if (asked.what === "app") await unwrap(api.POST("/api/two-step/app/remove", { body }));
      else await unwrap(api.POST("/api/two-step/passkeys/{passkey_id}/remove", { params: { path: { passkey_id: asked.id } }, body }));
      setAsking(null);
      setPassword("");
      if (asked.what !== "codes") toast({ message: asked.what === "app" ? "Authenticator app turned off." : `${asked.name} removed.` });
    },
    [TWO_STEP, ["me"]],
  );

  const passwordForm = (asked: Asking) => {
    const action = asked.what === "replace" ? replacePasskey : withPassword;
    return (
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (asked.what === "replace") replacePasskey.mutate({ id: asked.id, name: asked.name });
          else withPassword.mutate(asked);
        }}
      >
        <Field
          label="Your password"
          hint={
            asked.what === "codes"
              ? "To make new recovery codes. The ones you have stop working."
              : asked.what === "app"
                ? "To turn off your authenticator app."
                : asked.what === "replace"
                  ? `To replace ${asked.name} with a new passkey on this device, which signs you in alone. Your browser asks you to confirm next.`
                  : `To remove ${asked.name}.`
          }
        >
          <Input type="password" required autoFocus autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorText error={action.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant={asked.what === "codes" || asked.what === "replace" ? "primary" : "danger"} disabled={action.isPending}>
            {asked.what === "codes" ? "Make new codes" : asked.what === "app" ? "Turn off" : asked.what === "replace" ? "Replace" : "Remove"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setAsking(null);
              action.reset();
            }}
          >
            Cancel
          </Button>
        </div>
      </form>
    );
  };

  const canMake = (s: TwoStep) => s.passkeys_available && browserSupportsWebAuthn();
  const passkeys = (s: TwoStep) => (
    <section aria-label="Passkeys" className="flex flex-col gap-2">
      <SectionLabel>Passkeys</SectionLabel>
      {s.passkeys.length > 0 && (
        <ul className="divide-y divide-ash/50">
          {s.passkeys.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <span className="text-parchment">{p.name}</span>{" "}
                <span className="text-mist">
                  · added {dates.date(p.created_at)}
                  {p.last_used_at && `, last used ${dates.date(p.last_used_at)}`}
                </span>
                {aloneNote(p.discoverable) && <span className="mt-1 block text-mist">{aloneNote(p.discoverable)}</span>}
                {aloneNote(p.discoverable) && canMake(s) && (
                  <Button
                    type="button"
                    variant="secondary"
                    className="mt-2 min-h-8 px-2"
                    aria-label={`Replace this passkey, ${p.name}`}
                    disabled={replacePasskey.isPending}
                    onClick={() => {
                      replacePasskey.reset();
                      setAsking({ what: "replace", id: p.id, name: p.name });
                    }}
                  >
                    Replace this passkey
                  </Button>
                )}
              </div>
              <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove ${p.name}`} onClick={() => setAsking({ what: "passkey", id: p.id, name: p.name })}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      {(asking?.what === "passkey" || asking?.what === "replace") && passwordForm(asking)}
      {asking?.what === "passkey" || asking?.what === "replace" ? null : !s.passkeys_available ? (
        <p className="text-mist">Passkeys need this site on https.</p>
      ) : !browserSupportsWebAuthn() ? (
        <p className="text-mist">This browser can't make passkeys. An authenticator app works anywhere.</p>
      ) : (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            addPasskey.mutate(undefined);
          }}
        >
          <Field label="Passkey name" hint="So you can tell them apart, such as Phone.">
            <Input value={name} maxLength={60} placeholder="Passkey" onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Your password" hint="Asked again, so a sign-in left open can't add one.">
            <Input type="password" required autoComplete="current-password" value={addingPassword} onChange={(e) => setAddingPassword(e.target.value)} />
          </Field>
          <Button type="submit" variant={s.passkeys.length ? "secondary" : "primary"} disabled={addPasskey.isPending}>
            Add a passkey
          </Button>
        </form>
      )}
      <ErrorText error={addPasskey.error} />
    </section>
  );

  const app = (s: TwoStep) => (
    <section aria-label="Authenticator app" className="flex flex-col gap-2">
      <SectionLabel>Authenticator app</SectionLabel>
      {setup ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            confirm.mutate(undefined);
          }}
        >
          <p>Scan this with your authenticator app, or type the key into it. Then give the 6-digit code it shows.</p>
          <QrCode text={setup.uri} label="QR code for your authenticator app" className="w-44 self-center sm:self-start" />
          <p>
            Key: <span className="font-mono break-all text-parchment">{spaced(setup.secret)}</span>
          </p>
          <Field label="Code from your app">
            <Input required autoComplete="one-time-code" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <ErrorText error={confirm.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={confirm.isPending}>
              Turn on two-step sign-in
            </Button>
            <Button type="button" variant="secondary" onClick={() => setSetup(null)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : s.app ? (
        <>
          <p className="flex flex-wrap items-center gap-2">
            <Badge tone="gold">On</Badge> Authenticator app set up.
          </p>
          {asking?.what === "app" ? (
            passwordForm(asking)
          ) : (
            <Button type="button" variant="secondary" className="self-start" onClick={() => setAsking({ what: "app" })}>
              Turn off
            </Button>
          )}
        </>
      ) : s.apps_available ? (
        <>
          <p className="text-mist">A 6-digit code from an app such as Google Authenticator, Microsoft Authenticator or 1Password.</p>
          <ErrorText error={start.error} />
          <Button type="button" variant="secondary" className="self-start" disabled={start.isPending} onClick={() => start.mutate(undefined)}>
            Set up an authenticator app
          </Button>
        </>
      ) : (
        <p className="text-mist">Authenticator apps can't be set up on this server yet. Ask the custodian.</p>
      )}
    </section>
  );

  return (
    <Card title="Two-step sign-in">
      <Loaded query={state}>
        {(s) => (
          <div className="flex flex-col gap-4 text-sm">
            <p className="text-mist">
              After your password, Horatio asks for a second step: a passkey on your phone or computer, or a code from an authenticator app. Someone who learns your password still can't sign in as
              you. A passkey can also sign you in alone, with no password: choose <strong>Sign in with a passkey</strong>. Your password still works, and stays.
            </p>
            {s.required_by.length > 0 && <Notice>You need two-step sign-in as {s.required_by.join(" and as ")}.</Notice>}
            {codes ? (
              <RecoveryCodes
                codes={codes}
                onDone={() => {
                  setCodes(null);
                  onDone?.();
                }}
              />
            ) : (
              <>
                {passkeys(s)}
                {app(s)}
                {(s.app || s.passkeys.length > 0) && (
                  <section aria-label="Recovery codes" className="flex flex-col gap-2">
                    <SectionLabel>Recovery codes</SectionLabel>
                    <p>{s.recovery_codes_left} of 10 recovery codes left.</p>
                    {asking?.what === "codes" ? (
                      passwordForm(asking)
                    ) : (
                      <Button type="button" variant="secondary" className="self-start" onClick={() => setAsking({ what: "codes" })}>
                        New recovery codes
                      </Button>
                    )}
                  </section>
                )}
              </>
            )}
          </div>
        )}
      </Loaded>
    </Card>
  );
}

/** The recovery codes, shown once, to keep somewhere safe. */
function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const me = useMe();
  const download = () => {
    const text = `Horatio recovery codes for @${me.data?.handle ?? ""}\nEach works once, in place of your passkey or authenticator app.\n\n${codes.join("\n")}\n`;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    link.download = "horatio-recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return (
    <div className="flex flex-col gap-3">
      <Notice>Keep these recovery codes somewhere safe, away from your phone. Each signs you in once if you lose your passkeys and authenticator app. They aren't shown again.</Notice>
      <ul aria-label="Recovery codes" className="grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-parchment sm:grid-cols-3">
        {codes.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={download}>
          Download
        </Button>
        <Button type="button" variant="secondary" onClick={() => void navigator.clipboard?.writeText(codes.join("\n"))}>
          Copy
        </Button>
        <Button type="button" onClick={onDone}>
          I've kept them
        </Button>
      </div>
    </div>
  );
}
