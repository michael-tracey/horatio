import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { NotificationSettingsOut, NotificationTopicOut, Preferences } from "../../api/types";
import { Checkbox } from "../../components/Checkbox";
import { SettingCard } from "../../components/SettingCard";
import { SettingRow } from "../../components/SettingRow";
import { useToast } from "../../components/Toast";
import { Toggle } from "../../components/Toggle";
import { Button, ErrorText, Input, Loading, Notice, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction, usePreferences } from "../../hooks";
import { blocked, pushSupport, subscribeHere, subscriptionHere } from "../../offline/push";
import { ToldOfReports } from "../troupe/BoonReportsTold";
import { Choice, PreferenceCards, useSaveSetting, useScrollToHash } from "./PreferenceControls";

export const NOTIFICATION_SETTINGS = ["notification-settings"];

type Way = NotificationTopicOut["routes"][number]["way"];

const WAYS: Record<Way, string> = { bell: "Bell", email: "Email", push: "Phone" };

/**
 * Account › Notifications (#1053): every kind of notification Horatio sends you, grouped,
 * and where each comes, the bell, email or your phone (horatio.notification_choices). Some
 * always come, and say so. Phone notifications are turned on per device (#1054), here, with quiet
 * hours for them (#1196); emails come at once or in a digest a day or a week (#1196). Reported
 * boons go with a role: each troupe's switch is the one beside
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
  const { email, push, groups } = settings.data;
  const ways = [email && "email", push && "push"].filter((w): w is Way => !!w);
  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <p className="text-sm text-mist">
        Choose where each kind of notification comes: to the bell{email && ", by email"}
        {push && ", to your phone"}, or nowhere. Work waiting on you stays in the bell until it's done, and word about your account always comes.
      </p>
      {!email && <Notice>Email isn't set up on this server, so notifications don't come by email.</Notice>}
      {push ? (
        <>
          <PhoneCard settings={settings.data} />
          <QuietHours exempt={settings.data.quiet_exempt} />
        </>
      ) : (
        <Notice>Phone notifications aren't set up on this server, so none come to your phone.</Notice>
      )}
      {groups.map((group) => (
        <SettingCard key={group.name} title={group.title}>
          <div id={group.name} className="scroll-mt-4">
            {group.topics.map((topic) => (
              <TopicRow key={topic.name} topic={topic} ways={ways} />
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
function TopicRow({ topic, ways }: { topic: NotificationTopicOut; ways: Way[] }) {
  const toast = useToast();
  const client = useQueryClient();
  // The bell always; email and phone where this server can send them.
  const routes = topic.routes.filter((r) => r.way === "bell" || ways.includes(r.way));
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

/**
 * Phone notifications (#1054): on or off on this device, and every device where they're on.
 * Each kind ticked under Phone comes to each of them, even while Horatio is closed.
 */
function PhoneCard({ settings }: { settings: NotificationSettingsOut }) {
  const toast = useToast();
  const client = useQueryClient();
  const dates = useDates();
  const support = pushSupport();
  // This browser's subscription, once looked for; a device is "on" here if it is one of yours.
  const [here, setHere] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    void subscriptionHere().then((s) => setHere(s?.endpoint ?? null));
  }, []);
  const thisOne = settings.devices.find((d) => d.endpoint === here);
  const [chosen, setChosen] = useState<boolean | null>(null);
  const saved = (done: NotificationSettingsOut) => client.setQueryData<NotificationSettingsOut>(NOTIFICATION_SETTINGS, done);
  const turn = useAction(
    async (on: boolean) => {
      if (on) {
        const subscription = await subscribeHere(settings.push_key ?? "");
        saved(await unwrap(api.PUT("/api/notification-settings/devices", { body: subscription })));
        setHere(subscription.endpoint);
        toast({ message: "Phone notifications are on for this device." });
      } else {
        if (thisOne) saved(await turnOff(thisOne.id));
        await (await subscriptionHere())?.unsubscribe();
        setHere(null);
        toast({ message: "Phone notifications are off for this device." });
      }
    },
    [],
    { answered: [NOTIFICATION_SETTINGS] },
  );
  const forget = useAction(
    async ({ id, name }: { id: string; name: string }) => {
      saved(await turnOff(id));
      toast({ message: `Phone notifications are off for ${name}.` });
    },
    [],
    { answered: [NOTIFICATION_SETTINGS] },
  );
  const others = settings.devices.filter((d) => d !== thisOne);
  return (
    <SettingCard title="Phone notifications">
      {support === "yes" ? (
        <SettingRow
          label="On this device"
          hint={
            blocked() && !thisOne
              ? "This browser is set not to let Horatio notify you. Allow notifications for Horatio in its settings first."
              : "Each kind ticked under Phone below comes here, even while Horatio is closed. A tap opens it."
          }
          checked={chosen ?? !!thisOne}
          disabled={here === undefined || turn.isPending}
          onChange={(on) => {
            setChosen(on);
            turn.mutate(on, { onSettled: () => setChosen(null) });
          }}
        />
      ) : (
        <p className="py-3 text-sm text-mist">
          {support === "home-screen"
            ? "On an iPhone or iPad, add Horatio to your Home Screen first: in Safari, tap Share, then Add to Home Screen. Open Horatio from there, and turn phone notifications on here."
            : "This browser can't show notifications from Horatio. Try Chrome, Firefox, Edge or Safari."}
        </p>
      )}
      <ErrorText error={turn.error} />
      {others.length > 0 && (
        <div className="border-t border-ash/60 py-2 text-sm">
          <p className="py-1 text-mist">Also on:</p>
          <ul>
            {others.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-1">
                <span>
                  {d.name} <span className="text-mist">· since {dates.date(d.created_at)}</span>
                </span>
                <Button variant="secondary" disabled={forget.isPending} onClick={() => forget.mutate({ id: d.id, name: d.name })}>
                  Turn off
                </Button>
              </li>
            ))}
          </ul>
          <ErrorText error={forget.error} />
        </div>
      )}
    </SettingCard>
  );
}

function turnOff(id: string): Promise<NotificationSettingsOut> {
  return unwrap(api.DELETE("/api/notification-settings/devices/{device_id}", { params: { path: { device_id: id } } }));
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

const WEEKDAYS: [Preferences["digest_day"], string][] = [
  ["monday", "Monday"],
  ["tuesday", "Tuesday"],
  ["wednesday", "Wednesday"],
  ["thursday", "Thursday"],
  ["friday", "Friday"],
  ["saturday", "Saturday"],
  ["sunday", "Sunday"],
];

/** "8 am", or "08:00" on a 24-hour clock. */
export function hourName(hour: number, clock: Preferences["clock"]): string {
  if (clock === "24") return `${String(hour).padStart(2, "0")}:00`;
  return `${hour % 12 || 12} ${hour < 12 ? "am" : "pm"}`;
}

/** The person's time zone, as a hint names it. */
function zoneOf(prefs: Preferences): string {
  return prefs.time_zone ? prefs.time_zone.replaceAll("_", " ") : "UTC, until you choose a time zone under Preferences";
}

/** At once, or gathered into one email a day or a week, at the hour and on the day chosen (#106, #1196). */
function DigestRow() {
  const prefs = usePreferences();
  const save = useSaveSetting();
  const gathered = prefs.email_digest !== "at_once";
  return (
    <>
      <SettingRow label="Send emails" hint={digestHint(prefs)}>
        <Choice
          name="email_digest"
          label="Send emails"
          choices={[
            ["at_once", "At once"],
            ["daily", "Daily"],
            ["weekly", "Weekly"],
          ]}
        />
      </SettingRow>
      {prefs.email_digest === "weekly" && (
        <SettingRow label="On" short>
          <Select
            aria-label="Digest day"
            value={prefs.digest_day}
            onChange={(e) => {
              const day = e.target.value as Preferences["digest_day"];
              save({ digest_day: day }, `Digest day: ${WEEKDAYS.find(([d]) => d === day)?.[1]}`);
            }}
            className="text-sm"
          >
            {WEEKDAYS.map(([day, name]) => (
              <option key={day} value={day}>
                {name}
              </option>
            ))}
          </Select>
        </SettingRow>
      )}
      {gathered && (
        <SettingRow label="At" short>
          <Select
            aria-label="Digest hour"
            value={prefs.digest_hour}
            onChange={(e) => {
              const hour = Number(e.target.value);
              save({ digest_hour: hour }, `Digest hour: ${hourName(hour, prefs.clock)}`);
            }}
            className="text-sm"
          >
            {Array.from({ length: 24 }, (_, hour) => (
              <option key={hour} value={hour}>
                {hourName(hour, prefs.clock)}
              </option>
            ))}
          </Select>
        </SettingRow>
      )}
    </>
  );
}

export function digestHint(prefs: Preferences): string {
  const always = "Word about your account's safety, and announcements marked important, still come at once.";
  const at = hourName(prefs.digest_hour, prefs.clock);
  if (prefs.email_digest === "daily") return `One email a day at ${at} (${zoneOf(prefs)}), the day's notifications grouped by kind. ${always}`;
  if (prefs.email_digest === "weekly") {
    const day = WEEKDAYS.find(([d]) => d === prefs.digest_day)?.[1];
    return `One email a week, on ${day} at ${at} (${zoneOf(prefs)}), the week's notifications grouped by kind. ${always}`;
  }
  return "Each email as it happens. Daily or weekly gathers them into one email instead.";
}

/**
 * Quiet hours for phone notifications (#1196): from a time to a time in the person's time
 * zone, phone notifications wait, then come as one. The kinds the server names come anyway.
 */
function QuietHours({ exempt }: { exempt: string[] }) {
  const prefs = usePreferences();
  const save = useSaveSetting();
  const anyway = exempt.length ? ` ${list(exempt)} still come at once, as they matter at a game.` : "";
  return (
    <PreferenceCards id="quiet-hours">
      <SettingCard title="Quiet hours">
        <SettingRow
          label="Quiet hours"
          hint={`Phone notifications wait from the start to the end (${zoneOf(prefs)}), then come as one. The bell has them as they happen.${anyway}`}
          checked={prefs.quiet_hours}
          onChange={(on) => save({ quiet_hours: on }, `Quiet hours: ${on ? "on" : "off"}`)}
        />
        {prefs.quiet_hours && (
          <>
            <SettingRow label="From" short>
              <TimeField label="Quiet hours start" value={prefs.quiet_start} onSave={(at) => save({ quiet_start: at }, `Quiet hours from ${at}`)} />
            </SettingRow>
            <SettingRow label="Until" short>
              <TimeField label="Quiet hours end" value={prefs.quiet_end} onSave={(at) => save({ quiet_end: at }, `Quiet hours until ${at}`)} />
            </SettingRow>
          </>
        )}
      </SettingCard>
    </PreferenceCards>
  );
}

/** A time of day, saved once it's left with a whole time in it, or after a moment's pause:
 * a phone's time picker may never leave the field. */
function TimeField({ label, value, onSave }: { label: string; value: string; onSave: (at: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const save = useRef(onSave);
  save.current = onSave;
  const done = () => {
    clearTimeout(timer.current);
    if (/^\d\d:\d\d$/.test(text) && text !== value) onSave(text);
    else setText(value);
  };
  useEffect(() => {
    if (text === value || !/^\d\d:\d\d$/.test(text)) return;
    timer.current = setTimeout(() => save.current(text), 1500);
    return () => clearTimeout(timer.current);
  }, [text, value]);
  return (
    <Input
      type="time"
      aria-label={label}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={done}
      onKeyDown={(e) => e.key === "Enter" && done()}
      className="text-sm"
    />
  );
}

/** "A", "A and B", "A, B and C". */
function list(names: string[]): string {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
}

function LockIcon() {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="4.5" y="9" width="11" height="8" rx="1.5" />
      <path d="M7 9V6.5a3 3 0 0 1 6 0V9" strokeLinecap="round" />
    </svg>
  );
}
