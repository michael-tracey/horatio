import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router";
import { browserSupportsWebAuthn, browserSupportsWebAuthnAutofill, startAuthentication, WebAuthnAbortService } from "@simplewebauthn/browser";
import { api, ApiError, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, Card, ErrorText, Field, Input, Loading, Notice } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { manualLink } from "../manualLink";
import { useNext, withNext } from "../next";
import { passkeyAborted, passkeyProblem } from "../passkeys";
import { useTitle } from "../title";
import { DiscordSignIn } from "./DiscordSignIn";

export function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  useTitle(title);
  return (
    <div className="mx-auto mt-2 max-w-sm sm:mt-8">
      <img src="/logo.webp" alt="Horatio: MET legacy LARP tools" width={224} height={224} className="mx-auto mb-2 h-auto w-28 sm:w-56" />
      <p className="mb-4 text-center text-sm text-parchment sm:mb-2">Character sheets and downtimes for Mind's Eye Theatre troupes.</p>
      {/* A phone keeps its first screen for the form. */}
      <p className="mb-6 hidden text-center text-sm text-mist italic sm:block">"Alas, poor Yorick! I knew him, Horatio."</p>
      <Card title={title}>{children}</Card>
    </div>
  );
}

type SecondStep = components["schemas"]["SecondStep"];

/** Where a right password goes: on, or to give the account's second step (#1057). */
function useAfterPassword() {
  const navigate = useNavigate();
  const next = useNext();
  return (answer: object) => ("second_step" in answer ? navigate(withNext("/sign-in/second-step", next), { state: answer }) : navigate(next ?? "/characters"));
}

/** Sign in with a passkey alone, no password (#1098): the server's challenge, which
 * names no account, signed by whichever passkey the person picks. The device checks
 * their face, finger or PIN, so no second step follows. With `autofill`, the browser
 * offers their passkeys from the login box rather than at once. */
async function pickPasskey(autofill: boolean) {
  const optionsJSON = await unwrap(api.POST("/api/auth/passkey/options"));
  return startAuthentication({ optionsJSON: optionsJSON as never, useBrowserAutofill: autofill });
}

/** The picked passkey, for the server to sign the person in with. */
async function signInWithPasskey(credential: unknown) {
  await unwrap(api.POST("/api/auth/passkey", { body: { credential: credential as never } }));
}

export function SignInPage() {
  const me = useMe();
  const next = useNext();
  const navigate = useNavigate();
  const client = useQueryClient();
  const afterPassword = useAfterPassword();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useAction(async () => {
    afterPassword(await unwrap(api.POST("/api/auth/login", { body: { login, password } })));
  });
  const withPasskey = browserSupportsWebAuthn();
  const passkey = useAction(async () => {
    await signInWithPasskey(await pickPasskey(false));
    navigate(next ?? "/characters");
  });
  // The browser offers passkeys from the login box too (conditional UI), until one is
  // picked; again after the button's request ends, which took its place. The offer
  // itself going wrong stays off the page, in the console at most (#1124): no one
  // asked for it, and some browsers turn it down as the page opens. A passkey picked
  // from it that the server refuses is said, as for the button.
  const [offered, setOffered] = useState(0);
  const [refused, setRefused] = useState<unknown>(null);
  useEffect(() => {
    let on = true;
    void (async () => {
      try {
        if (!(await browserSupportsWebAuthnAutofill())) return;
        while (on) {
          const credential = await pickPasskey(true);
          if (!on) return;
          try {
            await signInWithPasskey(credential);
          } catch (error) {
            if (!on) return;
            setRefused(error);
            // Its challenge timed out: offer them again with a new one.
            if (error instanceof ApiError && error.status === 410) continue;
            return;
          }
          if (!on) return;
          await client.invalidateQueries();
          navigate(next ?? "/characters");
          return;
        }
      } catch (error) {
        if (on && !passkeyAborted(error)) console.info("The login box's passkey offer ended:", error);
      }
    })();
    return () => {
      on = false;
      WebAuthnAbortService.cancelCeremony();
    };
  }, [offered, client, navigate, next]);

  if (me.data) return <Navigate to={next ?? "/characters"} replace />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    signIn.mutate(undefined);
  };
  return (
    <Shell title="Sign in">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Email or handle">
          {/* "webauthn" lets the browser offer passkeys here (#1098). */}
          <Input autoComplete="username webauthn" autoCapitalize="none" spellCheck={false} required value={login} onChange={(e) => setLogin(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Link to={withNext("/forgot-password", next)} className="-mt-2 self-end text-sm text-gold underline">
          Forgot your password?
        </Link>
        <ErrorText error={signIn.error} />
        <Button type="submit" disabled={signIn.isPending}>
          Sign in
        </Button>
        {withPasskey && (
          <>
            <p className="text-center text-sm text-mist">or</p>
            <Button
              type="button"
              variant="secondary"
              disabled={passkey.isPending}
              onClick={() => {
                setRefused(null);
                passkey.mutate(undefined, { onError: () => setOffered((n) => n + 1) });
              }}
            >
              Sign in with a passkey
            </Button>
            <ErrorText error={passkeyProblem(passkey.error ?? refused)} />
          </>
        )}
        <DiscordSignIn verb="in" />
        <p className="text-center text-sm text-mist">
          New here?{" "}
          <Link to={withNext("/sign-up", next)} className="text-gold underline">
            Create an account
          </Link>
        </p>
        <p className="text-center text-sm text-mist">
          Not sure how it works?{" "}
          <Link to={manualLink("getting-started")} className="text-gold underline">
            Read the manual
          </Link>
        </p>
      </form>
    </Shell>
  );
}

export function SignUpPage() {
  const navigate = useNavigate();
  const next = useNext();
  const [form, setForm] = useState({ display_name: "", handle: "", email: "", password: "" });
  const signUp = useAction(async () => {
    await unwrap(api.POST("/api/auth/signup", { body: form }));
    navigate(next ?? "/characters");
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });

  return (
    <Shell title="Create an account">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          signUp.mutate(undefined);
        }}
        className="flex flex-col gap-4"
      >
        <Field label="Your name">
          <Input required autoComplete="name" value={form.display_name} onChange={set("display_name")} />
        </Field>
        <Field label="Handle" hint="How others find you, instead of your email. Letters, numbers, _ and -. Leave it blank for one made from your name.">
          <Input autoComplete="off" autoCapitalize="none" spellCheck={false} value={form.handle} onChange={set("handle")} />
        </Field>
        <Field label="Email" hint="Only you and the custodian see it.">
          <Input type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Password" hint="At least 10 characters.">
          <Input type="password" required minLength={10} autoComplete="new-password" value={form.password} onChange={set("password")} />
        </Field>
        <ErrorText error={signUp.error} />
        <Button type="submit" disabled={signUp.isPending}>
          Create account
        </Button>
        <DiscordSignIn verb="up" />
        <p className="text-center text-sm text-mist">
          Already have one?{" "}
          <Link to={withNext("/sign-in", next)} className="text-gold underline">
            Sign in
          </Link>
        </p>
      </form>
    </Shell>
  );
}

/**
 * The second step of signing in (#1057), once the password was right: a code from
 * their authenticator app, or one of their recovery codes. Five wrong, or ten
 * minutes, and the sign-in is over: back to the password.
 */
export function SecondStepPage() {
  const me = useMe();
  const navigate = useNavigate();
  const next = useNext();
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  // The ways in come with the password's answer; asked of the server only on a reload.
  const { state } = useLocation() as { state: SecondStep | null };
  const waiting = useQuery({
    queryKey: ["second-step"],
    queryFn: () => unwrap(api.GET("/api/auth/second-step")),
    enabled: !state?.second_step,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  const give = useAction(async () => {
    await unwrap(api.POST("/api/auth/second-step", { body: { code } }));
    navigate(next ?? "/characters");
  });
  const passkey = useAction(async () => {
    const optionsJSON = await unwrap(api.POST("/api/auth/second-step/passkey/options"));
    // The browser asks for the person's face, finger or PIN.
    const credential = await startAuthentication({ optionsJSON: optionsJSON as never });
    await unwrap(api.POST("/api/auth/second-step/passkey", { body: { credential: credential as never } }));
    navigate(next ?? "/characters");
  });
  // Timed out, or too many wrong codes: start again from the password.
  const failed = (state?.second_step ? null : waiting.error) ?? give.error ?? passkey.error;
  const over = failed instanceof ApiError && failed.status === 410;
  const ways = state?.second_step ?? waiting.data?.second_step ?? [];
  // A passkey first where there is one; a code from the app, or a recovery code in their place.
  const withPasskey = !recovery && ways.includes("passkey") && browserSupportsWebAuthn();
  const withCode = recovery || ways.includes("app") || (ways.includes("passkey") && !browserSupportsWebAuthn());

  if (me.data) return <Navigate to={next ?? "/characters"} replace />;
  return (
    <Shell title="Two-step sign-in">
      {!state?.second_step && waiting.isPending ? (
        <Loading />
      ) : over ? (
        <div className="flex flex-col gap-4">
          <ErrorText error={failed} />
          <Link to={withNext("/sign-in", next)} className="text-center text-sm text-gold underline">
            Sign in again
          </Link>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            give.mutate(undefined);
          }}
          className="flex flex-col gap-4"
        >
          {withPasskey && (
            <>
              <Button type="button" disabled={passkey.isPending} onClick={() => passkey.mutate(undefined)}>
                Use a passkey
              </Button>
              <ErrorText error={passkey.error} />
              {withCode && <p className="text-center text-sm text-mist">or</p>}
            </>
          )}
          {withCode && (
            <>
              <p className="text-sm text-mist">
                {recovery
                  ? "Give one of the recovery codes you kept when you set up two-step sign-in. Each works once."
                  : "Open your authenticator app and give the 6-digit code it shows for Horatio."}
              </p>
              <Field label={recovery ? "Recovery code" : "Code from your app"}>
                <Input
                  required
                  autoFocus
                  autoComplete="one-time-code"
                  autoCapitalize="none"
                  spellCheck={false}
                  inputMode={recovery ? "text" : "numeric"}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
              </Field>
              <ErrorText error={give.error} />
              <Button type="submit" variant={withPasskey ? "secondary" : "primary"} disabled={give.isPending}>
                Sign in
              </Button>
            </>
          )}
          {(ways.includes("app") || ways.includes("passkey")) && ways.includes("recovery_code") && (
            <button
              type="button"
              className="self-center text-sm text-gold underline"
              onClick={() => {
                setRecovery(!recovery);
                setCode("");
              }}
            >
              {recovery ? (ways.includes("app") ? "Use your authenticator app instead" : "Use your passkey instead") : "Use a recovery code instead"}
            </button>
          )}
          <p className="text-center text-sm text-mist">Lost them all? Ask the custodian to reset your two-step sign-in.</p>
        </form>
      )}
    </Shell>
  );
}

/** Ask for a reset link by email. The answer is the same whether or not an account
 * uses the address. Without email on the server, it says to ask the custodian. */
export function ForgotPasswordPage() {
  const next = useNext();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const help = useQuery({ queryKey: ["forgot"], queryFn: () => unwrap(api.GET("/api/auth/forgot")) });
  const ask = useAction(async () => {
    setSent((await unwrap(api.POST("/api/auth/forgot", { body: { email, next } }))).message);
  });
  const back = (
    <Link to={withNext("/sign-in", next)} className="text-center text-sm text-gold underline">
      Back to sign in
    </Link>
  );

  return (
    <Shell title="Forgot your password?">
      {help.isPending ? (
        <Loading />
      ) : help.error ? (
        <ErrorText error={help.error} />
      ) : !help.data.can_email ? (
        <div className="flex flex-col gap-4">
          <p className="text-sm">Horatio can't send email here, so ask the custodian to make you a reset link.</p>
          {back}
        </div>
      ) : sent ? (
        <div className="flex flex-col gap-4">
          <Notice>{sent}</Notice>
          <p className="text-sm text-mist">Nothing after a few minutes? Check your spam folder, or ask the custodian.</p>
          {back}
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask.mutate(undefined);
          }}
          className="flex flex-col gap-4"
        >
          <p className="text-sm text-mist">Give the address you sign in with, and Horatio will email you a link to set a new password.</p>
          <Field label="Email">
            <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <ErrorText error={ask.error} />
          <Button type="submit" disabled={ask.isPending}>
            Email me a link
          </Button>
          {back}
        </form>
      )}
    </Shell>
  );
}

/** Where a reset link lands, the custodian's or one asked for by email: set a new
 * password and be signed in. */
export function ResetPasswordPage() {
  const { token = "" } = useParams();
  const next = useNext();
  const afterPassword = useAfterPassword();
  const [password, setPassword] = useState("");
  const reset = useQuery({
    queryKey: ["reset", token],
    queryFn: () => unwrap(api.GET("/api/auth/reset/{token}", { params: { path: { token } } })),
    retry: false,
  });
  // With a second step, the new password is set, and the second step still asked.
  const save = useAction(async () => {
    afterPassword(await unwrap(api.POST("/api/auth/reset", { body: { token, password } })));
  });

  return (
    <Shell title="Set a new password">
      {reset.isPending ? (
        <Loading />
      ) : reset.error ? (
        <div className="flex flex-col gap-4">
          <ErrorText error={reset.error} />
          <Link to={withNext("/forgot-password", next)} className="text-center text-sm text-gold underline">
            Ask for a new link
          </Link>
          <Link to={withNext("/sign-in", next)} className="text-center text-sm text-gold underline">
            Back to sign in
          </Link>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
          className="flex flex-col gap-4"
        >
          <p className="text-sm text-mist">
            For {reset.data.display_name} ({reset.data.email}). This signs you out everywhere else.
          </p>
          {/* Lets a password manager save the new password against the right account. */}
          <input type="hidden" autoComplete="username" value={reset.data.email} readOnly />
          <Field label="New password" hint="At least 10 characters.">
            <Input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <ErrorText error={save.error} />
          <Button type="submit" disabled={save.isPending}>
            Set password and sign in
          </Button>
        </form>
      )}
    </Shell>
  );
}
