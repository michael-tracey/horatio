import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";
import { api, ApiError, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Button, ErrorText, Field, Input, Loading } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { useNext, withNext } from "../next";
import { Shell } from "./SignIn";

type SignUpFor = components["schemas"]["DiscordSignUpFor"];

/** Why Discord's callback left someone on the sign-in page (`?discord=`), in plain
 * words; null for anything Horatio didn't send, so a link can't put words here. */
export function discordOutcome(said: string | null): string | null {
  switch (said) {
    case "expired":
      return "That sign-in with Discord ran out of time, or was started in another browser. Try again.";
    case "cancelled":
      return "You cancelled on Discord, so you're not signed in.";
    case "failed":
      return "Discord didn't say who you are. Try again.";
    case "throttled":
      return "Too many sign-ins from here. Try again later.";
    case "no_email":
      return "Discord hasn't verified an email for your Discord account, so Horatio can't make you an account with it. Verify your email on Discord, then try again.";
    case "email_taken":
      return "An account here already uses your Discord account's email, but isn't linked to it. Sign in with your password, then link Discord in Account › Sign-in.";
    case "suspended":
      return "Your account is suspended. To ask about it, contact the custodian.";
    case "merged":
      return "That Discord account is linked to an account merged into another. Sign in to that one with its password, then link Discord in Account › Sign-in.";
    default:
      return null;
  }
}

/**
 * "Sign in with Discord" (#1128), on the sign-in and sign-up pages: only where Discord
 * is set up on the server. Discord says who they are; a Discord account no one here
 * has makes a new account, with the email Discord has verified. Where an account
 * has a second step, it is still asked for after Discord.
 */
export function DiscordSignIn({ verb }: { verb: "in" | "up" }) {
  const next = useNext();
  const [params] = useSearchParams();
  const help = useQuery({ queryKey: ["auth-discord"], queryFn: () => unwrap(api.GET("/api/auth/discord")) });
  const go = useAction(async () => {
    const { url } = await unwrap(api.POST("/api/auth/discord/start", { body: { next } }));
    window.location.assign(url);
  });
  const said = discordOutcome(params.get("discord"));

  if (!help.data?.available) return null;
  return (
    <>
      <p className="text-center text-sm text-mist">or</p>
      <Button type="button" variant="secondary" disabled={go.isPending} onClick={() => go.mutate(undefined)}>
        Sign {verb} with Discord
      </Button>
      <ErrorText error={go.error ?? said} />
    </>
  );
}

/**
 * The end of signing up with Discord (#1128): Discord has said who they are, and no
 * account here has their Discord account. They choose their name and handle, as
 * sign-up asks; the account uses the email Discord verified, and has no password.
 */
export function DiscordSignUpPage() {
  const me = useMe();
  const next = useNext();
  const waiting = useQuery({
    queryKey: ["auth-discord-sign-up"],
    queryFn: () => unwrap(api.GET("/api/auth/discord/sign-up")),
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });

  if (me.data) return <Navigate to={next ?? "/characters"} replace />;
  return (
    <Shell title="Sign up with Discord">
      {waiting.isPending ? (
        <Loading />
      ) : waiting.error ? (
        <div className="flex flex-col gap-4">
          <ErrorText error={waiting.error} />
          <Link to={withNext("/sign-up", next)} className="text-center text-sm text-gold underline">
            Start again
          </Link>
        </div>
      ) : (
        <DiscordSignUpForm said={waiting.data} />
      )}
    </Shell>
  );
}

function DiscordSignUpForm({ said }: { said: SignUpFor }) {
  const navigate = useNavigate();
  const next = useNext();
  const [form, setForm] = useState({ display_name: said.display_name, handle: said.handle });
  const signUp = useAction(async () => {
    await unwrap(api.POST("/api/auth/discord/sign-up", { body: form }));
    navigate(next ?? "/characters");
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [key]: e.target.value });
  const over = signUp.error instanceof ApiError && signUp.error.status === 410;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        signUp.mutate(undefined);
      }}
      className="flex flex-col gap-4"
    >
      <p className="text-sm text-mist">
        Discord says you're <span className="text-parchment">@{said.discord_username}</span>. Your account uses the email Discord has verified,{" "}
        <span className="text-parchment">{said.email}</span>, which only you and the custodian see. You'll sign in with Discord.
      </p>
      <Field label="Your name">
        <Input required autoComplete="name" value={form.display_name} onChange={set("display_name")} />
      </Field>
      <Field label="Handle" hint="How others find you, instead of your email. Letters, numbers, _ and -. Leave it blank for one made from your name.">
        <Input autoComplete="off" autoCapitalize="none" spellCheck={false} value={form.handle} onChange={set("handle")} />
      </Field>
      <ErrorText error={signUp.error} />
      {over ? (
        <Link to={withNext("/sign-up", next)} className="text-center text-sm text-gold underline">
          Start again
        </Link>
      ) : (
        <Button type="submit" disabled={signUp.isPending}>
          Create account
        </Button>
      )}
      <p className="text-center text-sm text-mist">
        Already have an account?{" "}
        <Link to={withNext("/sign-in", next)} className="text-gold underline">
          Sign in
        </Link>{" "}
        with your password, then link Discord in Account › Sign-in.
      </p>
    </form>
  );
}
