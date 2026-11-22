import { useQuery } from "@tanstack/react-query";
import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
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

/** Said where something asks for the password and the person has none, and no Discord
 * linked to confirm it's them instead (#1140). An account made with Discord (#1128) has
 * Discord linked, so this shouldn't happen, but it's said plainly if it does. `what`
 * says what asks for it, "Adding a passkey". */
export function NoPassword({ what }: { what: string }) {
  return (
    <p className="text-mist">
      {what} asks for your password, and you have none yet. Set one from{" "}
      <Link to="/forgot-password" className="text-gold underline">
        Forgot your password?
      </Link>
      , then come back.
    </p>
  );
}

/** What asks for the password again: setting up the app (#1148) or turning it off, new
 * codes, removing or replacing a passkey. Adding one asks for it in its own form. */
type Asking = { what: "setup" } | { what: "app" } | { what: "codes" } | { what: "passkey" | "replace"; id: string; name: string };

/** What someone with no password went to Discord to confirm it's them for (#1140): one
 * of the above, or adding a passkey. It goes there and back in the page's address. */
export type Confirming = "add" | Asking["what"];

// The address's words for it: `?confirming=` with the passkey's `passkey=` id, or the
// `name=` of a new one; and what Discord's callback said, `discord_confirm=`.
const CONFIRM_PARAMS = ["discord_confirm", "confirming", "passkey", "name"];

/** What Discord's callback said of confirming it's you (`?discord_confirm=`), in plain
 * words; null for anything else, so a crafted link can't put words on the page. */
export function confirmOutcome(said: string | null): { ok: boolean; text: string } | null {
  switch (said) {
    case "confirmed":
      return { ok: true, text: "Discord confirmed it's you. Go on within 5 minutes." };
    case "cancelled":
      return { ok: false, text: "Nothing was confirmed: you cancelled on Discord." };
    case "expired":
      return { ok: false, text: "That took too long. Confirm with Discord again." };
    case "other_account":
      return { ok: false, text: "That Discord account isn't the one linked to yours, so nothing was confirmed." };
    case "failed":
      return { ok: false, text: "Discord didn't say who you are, so nothing was confirmed. Try again." };
    case "throttled":
      return { ok: false, text: "Too many tries at confirming it's you. Try again later." };
    case "not_needed":
      return { ok: false, text: "You have a password now: give it instead." };
    default:
      return null;
  }
}

/** Where Discord sends them back to: this page, as it was, saying what they were doing. */
export function confirmNext(pathname: string, search: string, confirming: Confirming, extra: { passkey?: string; name?: string } = {}): string {
  const params = new URLSearchParams(search);
  for (const key of CONFIRM_PARAMS) params.delete(key);
  params.set("confirming", confirming);
  if (extra.passkey) params.set("passkey", extra.passkey);
  if (extra.name) params.set("name", extra.name);
  return `${pathname}?${params}`;
}

/** The form to open again, back from Discord: "add" for adding a passkey. A passkey
 * gone since is nothing. */
export function reopened(confirming: string | null, passkey: string | null, s: Pick<TwoStep, "passkeys">): Asking | "add" | null {
  if (confirming === "add") return "add";
  if (confirming === "setup" || confirming === "app" || confirming === "codes") return { what: confirming };
  if (confirming === "passkey" || confirming === "replace") {
    const found = s.passkeys.find((p) => p.id === passkey);
    return found ? { what: confirming, id: found.id, name: found.name } : null;
  }
  return null;
}

/** Whether this sign-in is confirmed with Discord now, standing in for a password the
 * person hasn't got (#1140). */
export function confirmedNow(s: Pick<TwoStep, "has_password" | "confirmed_until">, now = Date.now()): boolean {
  return !s.has_password && !!s.confirmed_until && Date.parse(s.confirmed_until) > now;
}

/** In place of the password, for someone with none and Discord linked (#1140): to
 * Discord and back to this page, with the form they were in open again, confirmed.
 * `children` sit beside the button, such as Cancel. */
function ConfirmWithDiscord({ confirming, passkey, name, children }: { confirming: Confirming; passkey?: string; name?: string; children?: React.ReactNode }) {
  const location = useLocation();
  const go = useAction(async () => {
    const next = confirmNext(location.pathname, location.search, confirming, { passkey, name });
    const { url } = await unwrap(api.POST("/api/auth/discord/confirm", { body: { next } }));
    window.location.assign(url);
  });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={go.isPending} onClick={() => go.mutate(undefined)}>
          Confirm with Discord
        </Button>
        {children}
      </div>
      <ErrorText error={go.error} />
    </div>
  );
}

/**
 * Two-step sign-in (#1057): after the password, a passkey on the person's phone or
 * computer, or a code from an authenticator app, with one-time recovery codes for
 * when both are lost. A passkey is made by the browser; an app is set up with a QR
 * code (and the key, to type in), then a code from it. The recovery codes come once,
 * with the first second step. Adding, replacing or removing a passkey, setting up or
 * turning off the app, or making new recovery codes, asks for the password again,
 * before the browser is asked for anything or the app's key is shown (#1110, #1148). Someone who must have it can't remove their last. A
 * passkey that may not sign in alone is replaced in one go: the new one is made and
 * kept before the old one goes, so a cancelled or failed try leaves the old one as it was.
 *
 * On Account › Sign-in it is "Your second steps" (#1193), with the linked Discord
 * account as `children`, after the recovery codes. Opened at `#passkeys`, as the offer
 * after a password sign-in does (PasskeyOffer), it goes to the form adding one.
 */
export function TwoStepCard({ onDone, title = "Two-step sign-in", children }: { onDone?: () => void; title?: string; children?: React.ReactNode }) {
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
  // Back from confirming with Discord (#1140): what it said, and the form they were
  // in, open again. The address forgets it, so going back or reloading doesn't redo it.
  const [params, setParams] = useSearchParams();
  const [told, setTold] = useState<{ ok: boolean; text: string } | null>(null);
  const toldRef = useRef<HTMLParagraphElement>(null);
  const loaded = state.data;
  // Sent to add a passkey (#1193): to the form, once the card has loaded.
  const { hash } = useLocation();
  const passkeysRef = useRef<HTMLElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (hash !== "#passkeys" || !loaded) return;
    passkeysRef.current?.scrollIntoView?.({ block: "start" });
    nameRef.current?.focus({ preventScroll: true });
  }, [hash, loaded]);
  useEffect(() => {
    const said = params.get("discord_confirm");
    if (!said || !loaded) return;
    setTold(confirmOutcome(said));
    const open = reopened(params.get("confirming"), params.get("passkey"), loaded);
    if (open === "add") setName(params.get("name") ?? "");
    else if (open) setAsking(open);
    const left = new URLSearchParams(params);
    for (const key of CONFIRM_PARAMS) left.delete(key);
    setParams(left, { replace: true });
  }, [params, loaded, setParams]);
  useEffect(() => {
    if (told) toldRef.current?.scrollIntoView?.({ block: "center" });
  }, [told]);

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
  const confirm = useAction(async () => {
    const made = await unwrap(api.POST("/api/two-step/app/confirm", { body: { code } }));
    setSetup(null);
    setCode("");
    turnedOn(made.recovery_codes, "Authenticator app turned on.");
  }, [TWO_STEP, ["me"]]);
  const withPassword = useAction(
    async (asked: Asking) => {
      const body = { password };
      if (asked.what === "setup") {
        setSetup(await unwrap(api.POST("/api/two-step/app", { body })));
        setCode("");
      } else if (asked.what === "codes") setCodes((await unwrap(api.POST("/api/two-step/recovery-codes", { body }))).recovery_codes);
      else if (asked.what === "app") await unwrap(api.POST("/api/two-step/app/remove", { body }));
      else await unwrap(api.POST("/api/two-step/passkeys/{passkey_id}/remove", { params: { path: { passkey_id: asked.id } }, body }));
      setAsking(null);
      setPassword("");
      if (asked.what === "passkey" || asked.what === "app") toast({ message: asked.what === "app" ? "Authenticator app turned off." : `${asked.name} removed.` });
    },
    [TWO_STEP, ["me"]],
  );

  const passwordForm = (asked: Asking, s: TwoStep) => {
    const action = asked.what === "replace" ? replacePasskey : withPassword;
    const what =
      asked.what === "setup"
        ? "Setting up an authenticator app"
        : asked.what === "codes"
          ? "Making new recovery codes"
          : asked.what === "app"
            ? "Turning off the app"
            : asked.what === "replace"
              ? `Replacing ${asked.name}`
              : `Removing ${asked.name}`;
    const hint =
      asked.what === "setup"
        ? "To set up an authenticator app. Its QR code and key show next."
        : asked.what === "codes"
          ? "To make new recovery codes. The ones you have stop working."
          : asked.what === "app"
            ? "To turn off your authenticator app."
            : asked.what === "replace"
              ? `To replace ${asked.name} with a new passkey on this device, which signs you in alone. Your browser asks you to confirm next.`
              : `To remove ${asked.name}.`;
    const cancel = (
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
    );
    const confirmed = confirmedNow(s);
    if (!s.has_password && !confirmed)
      return s.can_confirm_with_discord ? (
        <div className="flex flex-col gap-2">
          <p className="text-mist">{what} asks you to confirm it's you. You have no password, so confirm with Discord: Horatio sends you there and back to this form.</p>
          <ConfirmWithDiscord confirming={asked.what} passkey={"id" in asked ? asked.id : undefined}>
            {cancel}
          </ConfirmWithDiscord>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <NoPassword what={what} />
          <div>{cancel}</div>
        </div>
      );
    return (
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (asked.what === "replace") replacePasskey.mutate({ id: asked.id, name: asked.name });
          else withPassword.mutate(asked);
        }}
      >
        {confirmed ? (
          <p className="text-mist">{hint} Discord confirmed it's you, so no password is asked.</p>
        ) : (
          <Field label="Your password" hint={hint}>
            <Input type="password" required autoFocus autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
        )}
        <ErrorText error={action.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" variant={asked.what === "app" || asked.what === "passkey" ? "danger" : "primary"} disabled={action.isPending}>
            {asked.what === "setup" ? "Show the QR code" : asked.what === "codes" ? "Make new codes" : asked.what === "app" ? "Turn off" : asked.what === "replace" ? "Replace" : "Remove"}
          </Button>
          {cancel}
        </div>
      </form>
    );
  };

  const canMake = (s: TwoStep) => s.passkeys_available && browserSupportsWebAuthn();
  const passkeys = (s: TwoStep) => (
    <section id="passkeys" ref={passkeysRef} aria-label="Passkeys" className="flex scroll-mt-4 flex-col gap-2">
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
      {(asking?.what === "passkey" || asking?.what === "replace") && passwordForm(asking, s)}
      {asking?.what === "passkey" || asking?.what === "replace" ? null : !s.passkeys_available ? (
        <p className="text-mist">Passkeys need this site on https.</p>
      ) : !browserSupportsWebAuthn() ? (
        <p className="text-mist">This browser can't make passkeys. An authenticator app works anywhere.</p>
      ) : !s.has_password && !confirmedNow(s) ? (
        s.can_confirm_with_discord ? (
          <div className="flex flex-col gap-2">
            <p className="text-mist">
              Adding a passkey asks you to confirm it's you. You have no password, so confirm with Discord: Horatio sends you there and back, and you add it then.
            </p>
            <Field label="Passkey name" hint="So you can tell them apart, such as Phone.">
              <Input value={name} maxLength={60} placeholder="Passkey" onChange={(e) => setName(e.target.value)} />
            </Field>
            <ConfirmWithDiscord confirming="add" name={name.trim()} />
          </div>
        ) : (
          <NoPassword what="Adding a passkey" />
        )
      ) : (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            addPasskey.mutate(undefined);
          }}
        >
          <Field label="Passkey name" hint="So you can tell them apart, such as Phone.">
            <Input ref={nameRef} value={name} maxLength={60} placeholder="Passkey" onChange={(e) => setName(e.target.value)} />
          </Field>
          {s.has_password ? (
            <Field label="Your password" hint="Asked again, so a sign-in left open can't add one.">
              <Input type="password" required autoComplete="current-password" value={addingPassword} onChange={(e) => setAddingPassword(e.target.value)} />
            </Field>
          ) : (
            <p className="basis-full text-mist">Discord confirmed it's you, so no password is asked. Your browser asks you to make the passkey next.</p>
          )}
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
            passwordForm(asking, s)
          ) : (
            <Button type="button" variant="secondary" className="self-start" onClick={() => setAsking({ what: "app" })}>
              Turn off
            </Button>
          )}
        </>
      ) : s.apps_available ? (
        <>
          <p className="text-mist">A 6-digit code from an app such as Google Authenticator, Microsoft Authenticator or 1Password.</p>
          {asking?.what === "setup" ? (
            passwordForm(asking, s)
          ) : (
            <Button type="button" variant="secondary" className="self-start" onClick={() => setAsking({ what: "setup" })}>
              Set up an authenticator app
            </Button>
          )}
        </>
      ) : (
        <p className="text-mist">Authenticator apps can't be set up on this server yet. Ask the custodian.</p>
      )}
    </section>
  );

  return (
    <Card title={title}>
      <Loaded query={state}>
        {(s) => (
          <div className="flex flex-col gap-4 text-sm">
            <p className="text-mist">
              After your password, Horatio asks for a second step: a passkey on your phone or computer, or a code from an authenticator app. Someone who learns your password still can't sign in as
              you. A passkey can also sign you in alone, with no password: choose <strong>Sign in with a passkey</strong>. Your password still works, and stays.
            </p>
            {s.required_by.length > 0 && <Notice>You need two-step sign-in as {s.required_by.join(" and as ")}.</Notice>}
            {told && (
              <p ref={toldRef} role="status" className={`flex flex-wrap items-center gap-2 ${told.ok ? "text-parchment" : "text-blood-bright"}`}>
                {told.text}
                <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => setTold(null)}>
                  Dismiss
                </Button>
              </p>
            )}
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
                      passwordForm(asking, s)
                    ) : (
                      <Button type="button" variant="secondary" className="self-start" onClick={() => setAsking({ what: "codes" })}>
                        New recovery codes
                      </Button>
                    )}
                  </section>
                )}
                {children}
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
