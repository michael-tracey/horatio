import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { Preferences } from "../../api/types";
import { Card, ErrorText, Input } from "../../components/ui";
import { deviceZone, useDates } from "../../dates";
import { usePreferences, useSavingPreferences, useSetPreferences } from "../../hooks";
import { EmailNotifications } from "./EmailNotifications";
import { HandleCard } from "./HandleCard";

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

/** A setting with a few choices, as buttons side by side. */
export function Choice<K extends Key>({ name, label, choices }: { name: K; label: string; choices: [Preferences[K], string][] }) {
  const prefs = usePreferences();
  const set = useSetPreferences();
  return (
    <span role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-ash">
      {choices.map(([value, text]) => (
        <button
          key={String(value)}
          type="button"
          role="radio"
          aria-checked={prefs[name] === value}
          onClick={() => set.mutate({ [name]: value } as Partial<Preferences>)}
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
  const set = useSetPreferences();
  return (
    <label className="inline-flex min-h-9 items-center gap-2 text-sm text-mist">
      <input type="checkbox" className="h-5 w-5 accent-[var(--color-gold)]" checked={prefs[name]} onChange={(e) => set.mutate({ [name]: e.target.checked })} />
      <span className="sr-only">{label}</span>
      {prefs[name] ? "On" : "Off"}
    </label>
  );
}

/** Every IANA zone this browser knows, such as "America/New_York". */
function allZones(): string[] {
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return [...new Set([...zones, "UTC", deviceZone()])].sort();
}

/** The zone times show in: type to search the list, or leave it empty to follow this device. */
function TimeZone() {
  const prefs = usePreferences();
  const set = useSetPreferences();
  const zones = useMemo(allZones, []);
  const saved = prefs.time_zone ?? "";
  const [text, setText] = useState(saved);
  useEffect(() => setText(saved), [saved]);
  const choose = (zone: string | null) => {
    if (zone !== prefs.time_zone) set.mutate({ time_zone: zone });
  };
  return (
    <span className="flex flex-col items-start gap-1 sm:items-end">
      <Input
        type="search"
        aria-label="Time zone"
        list="time-zones"
        placeholder={`This device's (${deviceZone()})`}
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

/**
 * Settings for the signed-in person, saved on their account so they follow
 * them to their phone at game. Each takes effect as soon as it changes.
 */
export function SettingsPage() {
  const set = useSetPreferences();
  // Every control waits while a change is saved, so changes reach the server one
  // at a time and none is lost.
  const saving = useSavingPreferences();
  const slow = useAfter(saving, 200);
  return (
    <fieldset disabled={saving} aria-busy={saving} className={`grid min-w-0 gap-6 md:grid-cols-2 ${slow ? "cursor-wait opacity-60" : ""}`}>
      <p role="status" className="pointer-events-none fixed bottom-4 right-4 text-sm text-mist">
        {slow ? "Saving…" : ""}
      </p>
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
        <Setting label="Time zone" hint="Times show in this zone, wherever you are.">
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
          hint={"wakeLock" in navigator ? "While the Play View is open. Uses more battery." : "While the Play View is open. This browser can't, but your phone's may."}
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
        <Setting label="Light mode / Dark mode" hint="The World of Darkness is always dark.">
          <span role="radiogroup" aria-label="Light mode or dark mode" className="inline-flex cursor-not-allowed overflow-hidden rounded-md border border-ash opacity-50">
            <button type="button" role="radio" aria-checked={false} disabled className="min-h-9 px-3 text-sm text-mist">
              Light
            </button>
            <button type="button" role="radio" aria-checked disabled className="min-h-9 border-l border-ash bg-gold/20 px-3 text-sm text-gold">
              Dark
            </button>
          </span>
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

      <HandleCard />

      <EmailNotifications />

      <ErrorText error={set.error} />
    </fieldset>
  );
}
