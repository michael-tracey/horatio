import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import type { PlayerOut, Preferences } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Card, ErrorText, Input } from "../../components/ui";
import { deviceZone, useDates } from "../../dates";
import { usePreferences, useSavingPreferences, useSetPreferences } from "../../hooks";
import { AccountEmail } from "../AccountEmail";
import { saveAwake } from "../play/wakeLock";
import { ViewedAs } from "../ViewedAs";
import { EmailNotifications } from "./EmailNotifications";
import { PasswordCard } from "./PasswordCard";

type Key = keyof Preferences;

/** One setting: what it is, a hint, and its control. Shared with the cards in
 * their own files (EmailNotifications). */
export function Setting({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-ash/60 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-sm text-parchment">{label}</p>
        {hint && <p className="text-xs text-mist">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** Save a change to the settings, and say so once it is kept: "Paper: A4. Saved." */
function useSaveSetting() {
  const set = useSetPreferences();
  const toast = useToast();
  return (changes: Partial<Preferences>, said: string) =>
    set.mutate(changes, {
      onSuccess: () => toast({ message: `${said}. Saved.` }),
    });
}

/** A setting with a few choices, as buttons side by side. */
export function Choice<K extends Key>({ name, label, choices }: { name: K; label: string; choices: [Preferences[K], string][] }) {
  const prefs = usePreferences();
  const save = useSaveSetting();
  return (
    <span role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-ash">
      {choices.map(([value, text]) => (
        <button
          key={String(value)}
          type="button"
          role="radio"
          aria-checked={prefs[name] === value}
          onClick={() => save({ [name]: value } as Partial<Preferences>, `${label}: ${text}`)}
          className={`min-h-9 px-3 text-sm ${prefs[name] === value ? "bg-gold/20 text-gold" : "text-mist hover:text-parchment"} [&+&]:border-l [&+&]:border-ash`}
        >
          {text}
        </button>
      ))}
    </span>
  );
}

/** An on/off setting. */
function Toggle({ name, label }: { name: "quick_notes" | "keep_awake"; label: string }) {
  const prefs = usePreferences();
  const save = useSaveSetting();
  return (
    <label className="inline-flex min-h-9 items-center gap-2 text-sm text-mist">
      <input
        type="checkbox"
        className="h-5 w-5 accent-[var(--color-gold)]"
        checked={prefs[name]}
        onChange={(e) => {
          // The Play View's own switch on this device gives way to the setting just chosen.
          if (name === "keep_awake") saveAwake(null);
          save({ [name]: e.target.checked }, `${label}: ${e.target.checked ? "on" : "off"}`);
        }}
      />
      <span className="sr-only">{label}</span>
      {prefs[name] ? "On" : "Off"}
    </label>
  );
}

/** A zone as people read it: "America/New York". */
function zoneName(zone: string): string {
  return zone.replaceAll("_", " ");
}

/** Every IANA zone this browser knows, such as "America/New_York". */
function allZones(): string[] {
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return [...new Set([...zones, "UTC", deviceZone()])].sort();
}

/** The zone times show in: type to search the list, or leave it empty to follow this device. */
function TimeZone() {
  const prefs = usePreferences();
  const save = useSaveSetting();
  const zones = useMemo(allZones, []);
  const saved = prefs.time_zone ?? "";
  const [text, setText] = useState(saved);
  useEffect(() => setText(saved), [saved]);
  const choose = (zone: string | null) => {
    if (zone !== prefs.time_zone) save({ time_zone: zone }, `Time zone: ${zone ? zoneName(zone) : "this device's"}`);
  };
  return (
    <span className="flex flex-col items-start gap-1 sm:items-end">
      <Input
        type="search"
        aria-label="Time zone"
        list="time-zones"
        placeholder="Follow this device"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (zones.includes(e.target.value)) choose(e.target.value);
        }}
        // Left empty, times follow the device; left half-typed, the zone stays as it was.
        onBlur={() => (text.trim() ? setText(saved) : choose(null))}
        className="w-64 max-w-full text-sm"
      />
      <datalist id="time-zones">
        {zones.map((z) => (
          <option key={z} value={z} />
        ))}
      </datalist>
      {prefs.time_zone && (
        <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => choose(null)}>
          Use this device's
        </button>
      )}
    </span>
  );
}

/** The time now, as a downtime's deadline would show it with these settings. */
function DeadlineNow() {
  const dates = useDates();
  return <span className="text-sm text-parchment">{dates.deadline(new Date())}</span>;
}

/** True once `on` has stayed true for `ms`, so a quick save doesn't flash. */
function useAfter(on: boolean, ms: number): boolean {
  const [late, setLate] = useState(false);
  useEffect(() => {
    if (!on) return setLate(false);
    const timer = setTimeout(() => setLate(true), ms);
    return () => clearTimeout(timer);
  }, [on, ms]);
  return on && late;
}

/** Scroll to the part of the page the address names, such as #notifications from
 * the bell, once it is there. */
function useScrollToHash() {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [hash]);
}

/**
 * Settings for the signed-in person: which notifications come by email, their
 * email and password, then the settings saved on their account so they follow
 * them to their phone at game. Each of those takes effect as soon as it changes,
 * and a toast says it is kept.
 */
export function SettingsPage({ player }: { player: PlayerOut }) {
  const set = useSetPreferences();
  // Every control waits while a change is saved, so changes reach the server one
  // at a time and none is lost.
  const saving = useSavingPreferences();
  const slow = useAfter(saving, 200);
  const waiting = `min-w-0 ${slow ? "cursor-wait opacity-60" : ""}`;
  useScrollToHash();
  return (
    <div className="flex flex-col gap-6">
      <p role="status" className="pointer-events-none fixed bottom-4 right-4 text-sm text-mist">
        {slow ? "Saving…" : ""}
      </p>
      <div className="grid items-start gap-6 md:grid-cols-2">
        <fieldset id="notifications" disabled={saving} aria-busy={saving} className={`scroll-mt-4 ${waiting}`}>
          <EmailNotifications />
        </fieldset>
        <div className="flex min-w-0 flex-col gap-6">
          <AccountEmail player={player} />
          <PasswordCard />
          <ViewedAs />
        </div>
      </div>
      <fieldset disabled={saving} aria-busy={saving} className={`grid gap-6 md:grid-cols-2 ${waiting}`}>
        <Card title="Sheets">
          <Setting label="Show ratings as" hint="On character sheets, the Play View and printed sheets.">
            <Choice
              name="ratings"
              label="Show ratings as"
              choices={[
                ["numbers", "Numbers"],
                ["pips", "Pips"],
              ]}
            />
          </Setting>
          <Setting label="Paper" hint="What printed sheets and badges are laid out for.">
            <Choice
              name="paper"
              label="Paper"
              choices={[
                ["letter", "US Letter"],
                ["a4", "A4"],
              ]}
            />
          </Setting>
          <Setting label="Badge size" hint="To fit your badge holders. You can pick another size when you print.">
            <Choice
              name="badge_size"
              label="Badge size"
              choices={[
                ["3x5", "3 × 5 in"],
                ["3x4", "3 × 4 in"],
                ["cr80", "ID card"],
                ["4x6", "4 × 6 in"],
              ]}
            />
          </Setting>
        </Card>

        <Card title="Dates and times">
          <Setting label="Time zone" hint={`Times show in this zone, wherever you are. This device is on ${zoneName(deviceZone())} time.`}>
            <TimeZone />
          </Setting>
          <Setting label="Dates">
            <Choice
              name="date_format"
              label="Dates"
              choices={[
                ["day_month", "20 Oct 2026"],
                ["month_day", "10/20/2026"],
                ["iso", "2026-10-20"],
              ]}
            />
          </Setting>
          <Setting label="Clock">
            <Choice
              name="clock"
              label="Clock"
              choices={[
                ["12", "9:30 pm"],
                ["24", "21:30"],
              ]}
            />
          </Setting>
          <Setting label="Deadlines show as" hint="With their zone, so players elsewhere agree on them.">
            <DeadlineNow />
          </Setting>
        </Card>

        <Card title="At game">
          <Setting label="Quick notes" hint="The Play View asks what each use was for, except Blood, Willpower and healing.">
            <Toggle name="quick_notes" label="Quick notes" />
          </Setting>
          <Setting
            label="Keep the screen awake"
            hint={
              "wakeLock" in navigator
                ? "While the Play View is open. Uses more battery. The switch in the Play View changes it for one device."
                : "While the Play View is open. This browser can't, but your phone's may."
            }
          >
            <Toggle name="keep_awake" label="Keep the screen awake" />
          </Setting>
          <Setting label="The Play View opens on">
            <Choice
              name="play_tab"
              label="The Play View opens on"
              choices={[
                ["tracker", "Tracker"],
                ["sheet", "Sheet"],
                ["pools", "Pools"],
              ]}
            />
          </Setting>
        </Card>

        <Card title="Appearance">
          <Setting label="Text size" hint="Everywhere but printed sheets and badges.">
            <Choice
              name="text_size"
              label="Text size"
              choices={[
                ["normal", "Normal"],
                ["large", "Large"],
              ]}
            />
          </Setting>
        </Card>

        <Card title="Troupes">
          <Setting label="On a troupe's Who's Who, show me by" hint="Its players and staff see who plays each character.">
            <Choice
              name="whos_who_handle"
              label="On a troupe's Who's Who, show me by"
              choices={[
                [false, "My name"],
                [true, "My handle"],
              ]}
            />
          </Setting>
        </Card>
      </fieldset>
      <ErrorText error={set.error} />
    </div>
  );
}
