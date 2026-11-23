import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { Preferences } from "../../api/types";
import { drawCurtains } from "../../components/Curtains";
import { Segmented } from "../../components/Segmented";
import { SettingCard } from "../../components/SettingCard";
import { SettingRow } from "../../components/SettingRow";
import { startSunrise } from "../../components/Sunrise";
import { useToast } from "../../components/Toast";
import { ZonePicker, zoneWords } from "../../components/ZonePicker";
import { deviceZone, useDates } from "../../dates";
import { usePreferences } from "../../hooks";
import { useOnline } from "../../offline/connection";
import { tapsWaiting } from "../../offline/keep";
import { openingChoices, TABS } from "../play/tabs";
import { loadFlipping, saveFlipping } from "../play/flip";
import { saveAwake } from "../play/wakeLock";
import { Choice, PreferenceCards, useSaveSetting } from "./PreferenceControls";
import { ThrowPictures } from "./ThrowPictures";

// The tabs the Play View can open on, in the order offered.
const OPENING: Preferences["play_tab"][] = ["tracker", "sheet", "pools", "throws"];

/**
 * The tab the Play View opens on: only those at least one of the person's troupes has
 * on (#673), saying which troupe has switched one off. Where the tab chosen is off,
 * the Play View opens on its first tab.
 */
function OpeningTab() {
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const mine = (troupes.data ?? []).filter((t) => !t.archived && (t.my_role || t.my_characters.length > 0));
  const { offered, off } = openingChoices(OPENING, mine);
  const label = (tab: string) => TABS.find((t) => t.key === tab)?.label ?? tab;
  const hint =
    off.length > 0
      ? off.map((o) => `${o.troupes.join(" and ")} ${o.troupes.length > 1 ? "have" : "has"} switched off ${label(o.tab)}, so there it opens on the first tab on.`).join(" ")
      : undefined;
  return (
    <SettingRow label="The Play View opens on" hint={hint}>
      <Choice name="play_tab" label="The Play View opens on" choices={offered.map((tab) => [tab, label(tab)])} />
    </SettingRow>
  );
}

/**
 * Dark, light or Ultra goth. Horatio is only ever dark: choosing light lets the
 * sun rise on whoever is at the screen, who is signed out as they turn to ash
 * (Sunrise). Ultra goth, deep red on matte black, is kept on the account (#635):
 * velvet curtains close, it is saved behind them, and they open on it. Back to
 * Dark is a plain switch.
 */
function Theme() {
  // A person's settings kept on this device before there were themes have none.
  const theme = usePreferences().theme ?? "dark";
  const save = useSaveSetting();
  const toast = useToast();
  const online = useOnline();
  const dawn = () => {
    const waiting = tapsWaiting();
    if (waiting) toast({ message: `Not yet: ${waiting === 1 ? "1 tap hasn't" : `${waiting} taps haven't`} been sent.` });
    else if (!online) toast({ message: "Light mode needs a connection." });
    else startSunrise();
  };
  const goth = () => {
    if (theme === "ultragoth") return;
    // Saving needs the server: offline, the curtains would open on Dark again.
    if (!online) toast({ message: "Changing the theme needs a connection." });
    else drawCurtains(() => save({ theme: "ultragoth" }, "Theme: Ultra goth"));
  };
  const dark = () => {
    if (theme !== "dark") save({ theme: "dark" }, "Theme: Dark");
  };
  const choose = { dark, light: dawn, ultragoth: goth };
  return (
    <Segmented<keyof typeof choose>
      label="Theme"
      value={theme}
      options={[
        { value: "dark", label: "Dark" },
        // Never shown as chosen: the sun rises, and whoever is at the screen is signed out.
        { value: "light", label: "Light" },
        { value: "ultragoth", label: "Ultra goth" },
      ]}
      onChange={(value) => choose[value]()}
    />
  );
}

/** An on/off setting kept with the others. */
function PreferenceSwitch({ name, label, hint }: { name: "quick_notes" | "keep_awake"; label: string; hint?: ReactNode }) {
  const prefs = usePreferences();
  const save = useSaveSetting();
  return (
    <SettingRow
      label={label}
      hint={hint}
      checked={prefs[name]}
      onChange={(on) => {
        // The Play View's own switch on this device gives way to the setting just chosen.
        if (name === "keep_awake") saveAwake(null);
        save({ [name]: on }, `${label}: ${on ? "on" : "off"}`);
      }}
    />
  );
}

/** "Throw by flipping" (#669): kept on this device, not with the other settings, as it depends on the phone. */
function FlipSwitch({ hint }: { hint: ReactNode }) {
  const [on, setOn] = useState(loadFlipping);
  return (
    <SettingRow
      label="Throw by flipping"
      hint={hint}
      checked={on}
      onChange={(next) => {
        saveFlipping(next);
        setOn(next);
      }}
    />
  );
}

/** The zone times show in: type to search the list, or leave it empty to follow this device. */
function TimeZone() {
  const prefs = usePreferences();
  const save = useSaveSetting();
  return (
    <ZonePicker
      saved={prefs.time_zone ?? null}
      onChoose={(zone) => save({ time_zone: zone }, `Time zone: ${zone ? zoneWords(zone) : "this device's"}`)}
      placeholder="Follow this device"
      clearText="Use this device's"
    />
  );
}

/** The time now, as a downtime's deadline would show it with these settings. */
function DeadlineNow() {
  const dates = useDates();
  return <span className="text-sm text-parchment">{dates.deadline(new Date())}</span>;
}

/**
 * How Horatio looks and behaves for the signed-in person (#910): its look, sheets, dates
 * and times, the Play View at game, and how they show in their troupes. All kept on
 * their account, so they follow them to their phone at game.
 */
export function PreferencesPage() {
  return (
    <div className="max-w-2xl">
      <PreferenceCards>
        <SettingCard title="Appearance">
          <SettingRow label="Theme" short>
            <Theme />
          </SettingRow>
          <SettingRow label="Text size" hint="Everywhere but printed sheets and badges." short>
            <Choice
              name="text_size"
              label="Text size"
              choices={[
                ["normal", "Normal"],
                ["large", "Large"],
              ]}
            />
          </SettingRow>
        </SettingCard>

        <SettingCard title="Sheets">
          <SettingRow label="Show ratings as" hint="On character sheets, the Play View and printed sheets." short>
            <Choice
              name="ratings"
              label="Show ratings as"
              choices={[
                ["numbers", "Numbers"],
                ["pips", "Pips"],
              ]}
            />
          </SettingRow>
          <SettingRow label="Paper" hint="What printed sheets and badges are laid out for." short>
            <Choice
              name="paper"
              label="Paper"
              choices={[
                ["letter", "US Letter"],
                ["a4", "A4"],
              ]}
            />
          </SettingRow>
          <SettingRow label="Badge size" hint="To fit your badge holders. You can pick another size when you print.">
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
          </SettingRow>
        </SettingCard>

        <SettingCard title="Dates and times">
          <SettingRow label="Time zone" hint={`Times show in this zone, wherever you are. This device is on ${zoneWords(deviceZone())} time.`}>
            <TimeZone />
          </SettingRow>
          <SettingRow label="Dates">
            <Choice
              name="date_format"
              label="Dates"
              choices={[
                ["day_month", "20 Oct 2026"],
                ["month_day", "10/20/2026"],
                ["iso", "2026-10-20"],
              ]}
            />
          </SettingRow>
          <SettingRow label="Clock" short>
            <Choice
              name="clock"
              label="Clock"
              choices={[
                ["12", "9:30 pm"],
                ["24", "21:30"],
              ]}
            />
          </SettingRow>
          <SettingRow label="Deadlines show as" hint="With their zone, so players elsewhere agree on them.">
            <DeadlineNow />
          </SettingRow>
        </SettingCard>

        <SettingCard title="At game">
          <PreferenceSwitch name="quick_notes" label="Quick notes" hint="The Play View asks what each use was for, except Blood, Willpower and healing." />
          <PreferenceSwitch
            name="keep_awake"
            label="Keep the screen awake"
            hint={
              "wakeLock" in navigator
                ? "While the Play View is open. Uses more battery. The switch in the Play View changes it for one device."
                : "While the Play View is open. This browser can't, but your phone's may."
            }
          />
          <OpeningTab />
          <FlipSwitch hint="On the Throws tab, flip your phone face down and back up to throw. On this device, and only on phones with a motion sensor." />
          <SettingRow
            label="Throw pictures"
            hint="What the Throws tab shows: Horatio's, or the set of a troupe you play in that has made its own. Kept on this device for games with no signal."
          >
            <ThrowPictures />
          </SettingRow>
        </SettingCard>

        <SettingCard title="Troupes">
          <SettingRow label="On a troupe's Who's Who, show me by" hint="Its players and staff see who plays each character.">
            <Choice
              name="whos_who_handle"
              label="On a troupe's Who's Who, show me by"
              choices={[
                [false, "My name"],
                [true, "My handle"],
              ]}
            />
          </SettingRow>
        </SettingCard>
      </PreferenceCards>
    </div>
  );
}
