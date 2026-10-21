import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorText, Field, Input, Loading, Notice } from "../components/ui";
import { useAction, useMe } from "../hooks";

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto mt-2 max-w-sm sm:mt-8">
      <img src="/logo.webp" alt="Horatio: MET legacy LARP tools" width={224} height={224} className="mx-auto mb-2 h-auto w-44 sm:w-56" />
      <p className="mb-6 text-center text-sm text-mist italic">"Alas, poor Yorick! I knew him, Horatio."</p>
      <Card title={title}>{children}</Card>
    </div>
  );
}

export function SignInPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useAction(async () => {
    await unwrap(api.POST("/api/auth/login", { body: { login, password } }));
    navigate("/characters");
  });

  if (me.data) return <Navigate to="/characters" replace />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    signIn.mutate(undefined);
  };
  return (
    <Shell title="Sign in">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Email or handle">
          <Input autoComplete="username" autoCapitalize="none" spellCheck={false} required value={login} onChange={(e) => setLogin(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Link to="/forgot-password" className="-mt-2 self-end text-sm text-gold underline">
          Forgot your password?
        </Link>
        <ErrorText error={signIn.error} />
        <Button type="submit" disabled={signIn.isPending}>
          Sign in
        </Button>
        <p className="text-center text-sm text-mist">
          New here?{" "}
          <Link to="/sign-up" className="text-gold underline">
            Create an account
          </Link>
        </p>
      </form>
    </Shell>
  );
}

export function SignUpPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState({ display_name: "", handle: "", email: "", password: "" });
  const signUp = useAction(async () => {
    await unwrap(api.POST("/api/auth/signup", { body: form }));
    navigate("/characters");
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
        <p className="text-center text-sm text-mist">
          Already have one?{" "}
          <Link to="/sign-in" className="text-gold underline">
            Sign in
          </Link>
        </p>
      </form>
    </Shell>
  );
}

/** Ask for a reset link by email. The answer is the same whether or not an account
 * uses the address. Without email on the server, it says to ask the custodian. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const help = useQuery({ queryKey: ["forgot"], queryFn: () => unwrap(api.GET("/api/auth/forgot")) });
  const ask = useAction(async () => {
    setSent((await unwrap(api.POST("/api/auth/forgot", { body: { email } }))).message);
  });
  const back = (
    <Link to="/sign-in" className="text-center text-sm text-gold underline">
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
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const reset = useQuery({
    queryKey: ["reset", token],
    queryFn: () => unwrap(api.GET("/api/auth/reset/{token}", { params: { path: { token } } })),
    retry: false,
  });
  const save = useAction(async () => {
    await unwrap(api.POST("/api/auth/reset", { body: { token, password } }));
    navigate("/characters");
  });

  return (
    <Shell title="Set a new password">
      {reset.isPending ? (
        <Loading />
      ) : reset.error ? (
        <div className="flex flex-col gap-4">
          <ErrorText error={reset.error} />
          <Link to="/forgot-password" className="text-center text-sm text-gold underline">
            Ask for a new link
          </Link>
          <Link to="/sign-in" className="text-center text-sm text-gold underline">
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
