import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { NotificationSettingsOut, NotificationTopicOut, Preferences } from "../../api/types";
import { Checkbox } from "../../components/Checkbox";
import { SettingCard } from "../../components/SettingCard";
import { SettingRow } from "../../components/SettingRow";
import { useToast } from "../../components/Toast";
import { Toggle } from "../../components/Toggle";
import { ErrorText, Loading, Notice } from "../../components/ui";
import { useAction, usePreferences } from "../../hooks";
import { ToldOfReports } from "../troupe/BoonReportsTold";
import { Choice, PreferenceCards, useScrollToHash } from "./PreferenceControls";

export const NOTIFICATION_SETTINGS = ["notification-settings"];

type Way = NotificationTopicOut["routes"][number]["way"];

const WAYS: Record<Way, string> = { bell: "Bell", email: "Email" };

/**
 * Account › Notifications (#1053): every kind of notification Horatio sends you, grouped,
 * and where each comes, the bell or email (horatio.notification_choices). Some always
 * come, and say so. Reported boons go with a role: each troupe's switch is the one beside
 * the role (#1018), shown here too. What a troupe also sends to Discord or by its own email
 * is the troupe's choice, and is said, not chosen, but for each character's own channel on
 * its Discord, which its player can turn off (#1077). A way not listed never carries it.
 */
export function NotificationsPage() {
  useScrollToHash();
  const settings = useQuery({
    queryKey: NOTIFICATION_SETTINGS,
    queryFn: () => unwrap(api.GET("/api/notification-settings")),
  });
  if (settings.isPending) return <Loading />;
  if (settings.error) return <ErrorText error={settings.error} />;
  const { email, groups } = settings.data;
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <p className="text-sm text-mist">
        Choose where each kind of notification comes: to the bell, by email, both, or neither. Work waiting on you stays in the bell until it's done, and word about your account always
        comes.
      </p>
      {!email && <Notice>Email isn't set up on this server, so notifications come only to the bell.</Notice>}
      {groups.map((group) => (
        <SettingCard key={group.name} title={group.title}>
          <div id={group.name} className="scroll-mt-4">
            {group.topics.map((topic) => (
              <TopicRow key={topic.name} topic={topic} email={email} />
            ))}
          </div>
        </SettingCard>
      ))}
      {email && (
        <PreferenceCards id="digest">
          <SettingCard title="Emails">
            <DigestRow />
          </SettingCard>
        </PreferenceCards>
      )}
    </div>
  );
}

/** One kind of notification: what it is, and a tick for each way it can come. */
function TopicRow({ topic, email }: { topic: NotificationTopicOut; email: boolean }) {
  const toast = useToast();
  const client = useQueryClient();
  const routes = topic.routes.filter((r) => email || r.way !== "email");
  // Shown as chosen at once, while it saves.
  const [chosen, setChosen] = useState<{ way: Way; on: boolean } | null>(null);
  const choose = useAction(
    async ({ way, on }: { way: Way; on: boolean }) => {
      const done = await unwrap(api.PUT("/api/notification-settings", { body: { topic: topic.name, way, on } }));
      client.setQueryData<NotificationSettingsOut>(NOTIFICATION_SETTINGS, done);
      toast({ message: `${topic.title}, ${WAYS[way].toLowerCase()}: ${on ? "on" : "off"}. Saved.` });
    },
    [],
    { answered: [NOTIFICATION_SETTINGS] },
  );
  const hint = (
    <>
      {topic.hint}
      {topic.troupes_send.map((t) => (
        <span key={t.troupe_id} className="mt-1 block">
          {t.troupe_name} also sends them {sends(t.connectors)}: the troupe's choice.
        </span>
      ))}
    </>
  );
  if (!routes.length) return null;
  return (
    // The row's own line is its last child's: under the roles, where it has them.
    <div className="border-b border-ash/60 last:border-0">
      <SettingRow label={topic.title} hint={hint}>
        <div className="flex flex-wrap items-center gap-x-5">
          {routes.map((route) =>
            route.always ? (
              <span key={route.way} className="flex min-h-10 items-center gap-1.5 text-sm text-mist">
                <LockIcon />
                {WAYS[route.way]}, always
              </span>
            ) : (
              <Checkbox
                key={route.way}
                label={WAYS[route.way]}
                aria-label={`${topic.title}: ${WAYS[route.way].toLowerCase()}`}
                checked={chosen?.way === route.way ? chosen.on : route.on}
                disabled={choose.isPending}
                onChange={(on) => {
                  setChosen({ way: route.way, on });
                  choose.mutate({ way: route.way, on }, { onSettled: () => setChosen(null) });
                }}
              />
            ),
          )}
        </div>
      </SettingRow>
      <ErrorText error={choose.error} />
      {topic.roles && <Roles topic={topic} />}
      <OwnChannels topic={topic} />
    </div>
  );
}

/**
 * Each of your characters' own channels on a troupe's Discord (#1077): on until you turn it
 * off, for results and quest news alike. Off, nothing is posted there; the troupe's shared
 * channels are unchanged, and the results still come here.
 */
function OwnChannels({ topic }: { topic: NotificationTopicOut }) {
  const toast = useToast();
  const client = useQueryClient();
  const [chosen, setChosen] = useState<{ id: string; on: boolean } | null>(null);
  const save = useAction(
    async ({ id, on, name }: { id: string; on: boolean; name: string }) => {
      const done = await unwrap(api.PUT("/api/notification-settings/own-channel", { body: { character_id: id, on } }));
      client.setQueryData<NotificationSettingsOut>(NOTIFICATION_SETTINGS, done);
      toast({ message: on ? `Discord posts to ${name}'s channel again.` : `Discord won't post to ${name}'s channel.` });
    },
    [],
    { answered: [NOTIFICATION_SETTINGS] },
  );
  const channels = topic.troupes_send.flatMap((t) => t.own_channels.map((c) => ({ ...c, troupe: t.troupe_name })));
  if (!channels.length) return null;
  return (
    <div className="pb-2 pl-4 text-sm">
      {channels.map((c) => (
        <Toggle
          key={c.character_id}
          label={`${c.troupe}: post to ${c.character_name}'s own Discord channel`}
          hint="Results and quest news. Off, they still come here, as you choose above, and the troupe's own channels are unchanged."
          checked={chosen?.id === c.character_id ? chosen.on : c.on}
          disabled={save.isPending}
          onChange={(on) => {
            setChosen({ id: c.character_id, on });
            save.mutate({ id: c.character_id, on, name: c.character_name }, { onSettled: () => setChosen(null) });
          }}
        />
      ))}
      <ErrorText error={save.error} />
    </div>
  );
}

/** "to Discord", "by email", "to Discord and by email". */
function sends(connectors: string[]): string {
  const said = connectors.map((c) => (c === "Discord" ? "to Discord" : `by ${c.toLowerCase()}`));
  return said.length > 1 ? `${said.slice(0, -1).join(", ")} and ${said.at(-1)}` : (said[0] ?? "");
}

/** Whether you are told at all, for each role you hold (#1018): the same switch as beside the role. */
function Roles({ topic }: { topic: NotificationTopicOut }) {
  const roles = topic.roles ?? [];
  if (!roles.length)
    return <p className="pb-3 text-xs text-mist">You hold none of these roles now. Once you do, your choice for each troupe shows here.</p>;
  return (
    <div className="pb-2 pl-4">
      {roles.map((role) => (
        <ToldOfReports
          key={`${role.troupe_id}-${role.role}`}
          troupeId={role.troupe_id}
          as={role.role}
          label={role.role === "staff" ? `${role.troupe_name}: as staff` : `${role.troupe_name}: as ${role.office}, ${role.character_name}`}
          hint={role.role === "staff" ? "Off until you turn it on. Also in the troupe's Boons settings." : "On until you turn it off. Also on your ledger's To review tab in the Play View."}
        />
      ))}
    </div>
  );
}

/** At once, or one email a day (#106). */
function DigestRow() {
  const prefs = usePreferences();
  return (
    <SettingRow label="Send emails" hint={digestHint(prefs)} short>
      <Choice
        name="email_digest"
        label="Send emails"
        choices={[
          ["at_once", "At once"],
          ["daily", "Once a day"],
        ]}
      />
    </SettingRow>
  );
}

function digestHint(prefs: Preferences): string {
  const zone = prefs.time_zone ? prefs.time_zone.replaceAll("_", " ") : "UTC, until you choose a time zone";
  return `Once a day gathers them into one email at 8 am (${zone}).`;
}

function LockIcon() {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="4.5" y="9" width="11" height="8" rx="1.5" />
      <path d="M7 9V6.5a3 3 0 0 1 6 0V9" strokeLinecap="round" />
    </svg>
  );
}
