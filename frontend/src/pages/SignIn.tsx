import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorText, Field, Input, Loading } from "../components/ui";
import { useAction, useMe } from "../hooks";

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto mt-6 max-w-sm sm:mt-16">
      <p className="mb-6 text-center text-sm text-mist italic">"Alas, poor Yorick! I knew him, Horatio."</p>
      <Card title={title}>{children}</Card>
    </div>
  );
}

export function SignInPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const signIn = useAction(async () => {
    await unwrap(api.POST("/api/auth/login", { body: { email, password } }));
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
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
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
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
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
        <Field label="Email">
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

/** Where the custodian's reset link lands: set a new password and be signed in. */
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
