import { useEffect, useState, type ReactNode } from "react";
import type { Preferences } from "../../api/types";
import { Card, ErrorText, Select } from "../../components/ui";
import { usePreferences, useSavingPreferences, useSetPreferences } from "../../hooks";

type Key = keyof Preferences;

/** One setting: what it is, a hint, and its control. */
function Setting({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
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
function Choice<K extends Key>({ name, label, choices }: { name: K; label: string; choices: [Preferences[K], string][] }) {
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

function deviceZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function TimeZone() {
  const prefs = usePreferences();
  const set = useSetPreferences();
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [deviceZone()];
  return (
    <Select aria-label="Time zone" value={prefs.time_zone ?? ""} onChange={(e) => set.mutate({ time_zone: e.target.value || null })} className="max-w-64 text-sm">
      <option value="">This device's ({deviceZone()})</option>
      {zones.map((z) => (
        <option key={z} value={z}>
          {z.replaceAll("_", " ")}
        </option>
      ))}
    </Select>
  );
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
        <Setting label="Badge size" hint="To fit your badge holders.">
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
      </Card>

      <Card title="At game">
        <Setting label="Quick notes" hint="The Play View asks what each spend was for.">
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
        <Setting label="Text size">
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

      {/* #103: your handle goes here. */}

      {/* #106: notifications by email go here. */}

      <ErrorText error={set.error} />
    </fieldset>
  );
}
