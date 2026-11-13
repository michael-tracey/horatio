import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Badge, Button, Card, ErrorText, Field, Input, Loaded } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

type MailOut = components["schemas"]["SiteMailOut"];
type DiscordOut = components["schemas"]["SiteDiscordOut"];
type Failure = components["schemas"]["SiteFailure"];

const MAIL = ["site", "mail"];
const DISCORD = ["site", "discord"];

/** Where the credentials are, and how a change to them goes live. */
function Secrets({ where, names }: { where: string; names: string }) {
  return (
    <p className="text-xs text-mist">
      {names} live in <code className="text-parchment">{where}</code> on the server, never in Horatio's database. Change them there, then redeploy with{" "}
      <code className="text-parchment">deploy/deploy.sh --no-build</code>.
    </p>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-mist">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}

function SetOrNot({ set }: { set: boolean }) {
  return set ? <Badge tone="gold">Set</Badge> : <Badge>Not set</Badge>;
}

/**
 * Mail (#833): whether Horatio can send email, what it uses (never the password),
 * who emails come from, a test to the custodian's own address, and what failed lately.
 */
export function MailCard() {
  const mail = useQuery({ queryKey: MAIL, queryFn: () => unwrap(api.GET("/api/site/mail")) });
  return <Loaded query={mail}>{(found) => <MailShown mail={found} />}</Loaded>;
}

function MailShown({ mail }: { mail: MailOut }) {
  const security = { ssl: "SSL", starttls: "STARTTLS", none: "None" }[mail.security];
  return (
    <Card title="Mail" actions={<Badge tone={mail.on ? "gold" : "blood"}>{mail.on ? "Mail is set up" : "Mail is off"}</Badge>}>
      <div className="flex flex-col gap-4 text-sm">
        {!mail.on && <p className="text-parchment">Horatio sends no email: {mail.off_reason}</p>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
          <Row label="Mail server">{mail.host ? `${mail.host}, port ${mail.port}` : <span className="text-mist">Not set</span>}</Row>
          <Row label="Security">
            <span className="flex flex-col gap-1">
              {security}
              {mail.security_note && <span className="text-xs text-blood-bright">{mail.security_note}</span>}
            </span>
          </Row>
          <Row label="Username">{mail.username ?? <span className="text-mist">None</span>}</Row>
          <Row label="Password">
            <SetOrNot set={mail.password_set} />
          </Row>
          <Row label="Emails come from">{mail.sends_from ?? <span className="text-mist">Nobody yet</span>}</Row>
        </dl>
        <Secrets where={mail.where} names="The mail server, its username and password" />
        <SenderForm mail={mail} />
        {mail.on && <TestEmail />}
        <Failures title="Mail that failed lately" failures={mail.failures} queryKey={MAIL} />
      </div>
    </Card>
  );
}

/** The From name and address over the server's, and a default Reply-To. */
function SenderForm({ mail }: { mail: MailOut }) {
  const toast = useToast();
  const [name, setName] = useState(mail.from_name ?? "");
  const [address, setAddress] = useState(mail.from_address ?? "");
  const [replyTo, setReplyTo] = useState(mail.reply_to ?? "");
  useEffect(() => {
    setName(mail.from_name ?? "");
    setAddress(mail.from_address ?? "");
    setReplyTo(mail.reply_to ?? "");
  }, [mail.from_name, mail.from_address, mail.reply_to]);
  const save = useAction(() => unwrap(api.PUT("/api/site/mail", { body: { from_name: name, from_address: address, reply_to: replyTo } })), [MAIL]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: () => toast({ message: "Saved. Every email from now on uses it." }) });
  };
  const server = mail.server_from ?? "the server's HORATIO_MAIL_FROM";
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t border-ash pt-4">
      <h3 className="text-parchment">Who emails come from</h3>
      <p className="text-xs text-mist">
        Blank uses the server's: {server}. The From address must be one your mail provider lets Horatio send from, or emails will be refused.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="From name">
          <Input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="From address">
          <Input type="email" value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field label="Reply-To" hint="Where replies go. A troupe's own, for its downtime results, wins.">
          <Input type="email" value={replyTo} onChange={(e) => setReplyTo(e.target.value)} />
        </Field>
      </div>
      <div>
        <Button type="submit" disabled={save.isPending}>
          Save who emails come from
        </Button>
      </div>
      <ErrorText error={save.error} />
    </form>
  );
}

function TestEmail() {
  const test = useAction(() => unwrap(api.POST("/api/site/mail/test")), [MAIL]);
  const result = test.data;
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" disabled={test.isPending} onClick={() => test.mutate(undefined)}>
          Send a test email
        </Button>
        <span className="text-xs text-mist">To your own address, now.</span>
      </div>
      <div role="status" className="flex flex-col gap-1">
        {result?.ok && <p className="text-parchment">Sent to {result.to}. If it doesn't arrive, look in its spam folder.</p>}
        {result && !result.ok && (
          <>
            <p className="text-blood-bright">{result.reason}</p>
            {result.detail && <p className="font-mono text-xs break-words text-mist">The server said: {result.detail}</p>}
          </>
        )}
      </div>
      <ErrorText error={test.error} />
    </div>
  );
}

/**
 * Discord (#834): whether the Horatio bot can work, what to paste into Discord's
 * developer portal, a check of the bot, the troupes connected, and what failed lately.
 */
export function DiscordCard() {
  const discord = useQuery({ queryKey: DISCORD, queryFn: () => unwrap(api.GET("/api/site/discord")) });
  return <Loaded query={discord}>{(found) => <DiscordShown discord={found} />}</Loaded>;
}

function DiscordShown({ discord }: { discord: DiscordOut }) {
  return (
    <Card title="Discord" actions={<Badge tone={discord.on ? "gold" : "blood"}>{discord.on ? "Discord is set up" : "Discord is off"}</Badge>}>
      <div className="flex flex-col gap-4 text-sm">
        {!discord.on && <p className="text-parchment">Troupes can't connect Discord until these are set: {discord.missing.join(", ")}.</p>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2">
          <Row label="Client ID">{discord.client_id ? <span className="font-mono">{discord.client_id}</span> : <span className="text-mist">Not set</span>}</Row>
          <Row label="Client secret">
            <SetOrNot set={discord.client_secret_set} />
          </Row>
          <Row label="Bot token">
            <SetOrNot set={discord.bot_token_set} />
          </Row>
        </dl>
        <Secrets where={discord.where} names="The client ID, client secret and bot token" />
        <div className="flex flex-col gap-3 border-t border-ash pt-4">
          <h3 className="text-parchment">For Discord's developer portal</h3>
          <Copyable label="OAuth2 redirect" hint="Add it under OAuth2 › Redirects, exactly as it is." value={discord.redirect} />
          {discord.invite && (
            <Copyable
              label="Invite link for the bot"
              hint="Adds the bot to a server by hand, asking for the four permissions Horatio uses (see Setting up Discord in the manual). A troupe connects its own server from its Connectors tab instead."
              value={discord.invite}
            />
          )}
        </div>
        {discord.bot_token_set && <CheckBot />}
        <ConnectedTroupes troupes={discord.troupes} />
        <Failures title="Discord posts that failed lately" failures={discord.failures} queryKey={DISCORD} />
      </div>
    </Card>
  );
}

function Copyable({ label, hint, value }: { label: string; hint: string; value: string }) {
  const id = useId();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
  };
  return (
    <div className="flex flex-col gap-1 text-sm">
      <label htmlFor={id} className="text-mist">
        {label}
      </label>
      <span className="flex flex-wrap items-center gap-2">
        <Input id={id} readOnly value={value} aria-describedby={`${id}-hint`} className="min-w-0 flex-1 font-mono text-xs" onFocus={(e) => e.target.select()} />
        <Button variant="secondary" onClick={copy} aria-label={`Copy the ${label}`}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </span>
      <span id={`${id}-hint`} className="text-xs text-mist">
        {hint}
      </span>
    </div>
  );
}

function CheckBot() {
  const check = useAction(() => unwrap(api.POST("/api/site/discord/check")));
  const bot = check.data;
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <div>
        <Button variant="secondary" disabled={check.isPending} onClick={() => check.mutate(undefined)}>
          Check the bot
        </Button>
      </div>
      <div role="status" className="flex flex-col gap-1">
        {bot?.ok && (
          <p className="text-parchment">
            Discord knows the bot as {bot.name}, in {bot.servers}
            {bot.more ? " or more" : ""} {bot.servers === 1 ? "server" : "servers"}.
          </p>
        )}
        {bot && !bot.ok && (
          <>
            <p className="text-blood-bright">{bot.reason}</p>
            {bot.detail && <p className="font-mono text-xs break-words text-mist">Discord said: {bot.detail}</p>}
          </>
        )}
      </div>
      <ErrorText error={check.error} />
    </div>
  );
}

function ConnectedTroupes({ troupes }: { troupes: DiscordOut["troupes"] }) {
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <h3 className="text-parchment">Troupes connected</h3>
      {troupes.length === 0 ? (
        <p className="text-mist">No troupe has connected a Discord server yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {troupes.map((t) => (
            <li key={t.troupe_id} className="flex flex-col">
              <span>
                <Link to={`/troupes/${t.troupe_id}/connectors`} className="text-gold hover:underline">
                  {t.troupe_name}
                </Link>
                {t.archived && <span className="text-mist"> (archived)</span>}
                {t.server && <span className="text-mist"> · {t.server}</span>}
              </span>
              <span className="text-xs text-mist">
                {t.characters} {t.characters === 1 ? "character's channel" : "characters' channels"} for results
                {t.test_channel ? ", a test channel" : ""}
                {t.posts.length ? `, posts: ${t.posts.join(" and ")}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What failed lately, newest first, with where it is and a Retry where the card can. */
function Failures({ title, failures, queryKey }: { title: string; failures: Failure[]; queryKey: string[] }) {
  const dates = useDates();
  const toast = useToast();
  const retry = useAction(async (f: Failure) => {
    if (f.retry === "post" && f.post_id) await unwrap(api.POST("/api/posts/{post_id}/discord/retry", { params: { path: { post_id: f.post_id } } }));
    else await unwrap(api.POST("/api/deliveries/{delivery_id}/retry", { params: { path: { delivery_id: f.id } } }));
  }, [queryKey]);
  return (
    <div className="flex flex-col gap-2 border-t border-ash pt-4">
      <h3 className="text-parchment">{title}</h3>
      {failures.length === 0 ? (
        <p className="text-mist">Nothing has failed lately.</p>
      ) : (
        <ul className="flex flex-col gap-3" aria-label={title}>
          {failures.map((f) => (
            <li key={f.id} className="flex flex-wrap items-start justify-between gap-2">
              <span className="flex min-w-0 flex-col">
                <span>
                  {f.link ? (
                    <Link to={f.link} className="text-gold hover:underline">
                      {f.about}
                    </Link>
                  ) : (
                    f.about
                  )}
                  {f.troupe_name && <span className="text-mist"> · {f.troupe_name}</span>}
                </span>
                <span className="text-xs break-words text-mist">
                  {dates.dateTime(f.at)} · {f.state === "failed" ? "Gave up" : "Trying again"} · {f.reason}
                </span>
              </span>
              {f.retry && (
                <Button
                  variant="secondary"
                  className="min-h-8 px-2"
                  disabled={retry.isPending}
                  aria-label={`Retry ${f.about}`}
                  onClick={() => retry.mutate(f, { onSuccess: () => toast({ message: "Horatio will try it again shortly." }) })}
                >
                  Retry
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={retry.error} />
    </div>
  );
}
