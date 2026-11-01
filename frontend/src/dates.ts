/**
 * Dates and times as each person likes them (issue #102): in the time zone they
 * chose, or the device's when they have not, written "20 Oct 2026", "10/20/2026"
 * or "2026-10-20", on a 12- or 24-hour clock. Every date and time Horatio shows
 * goes through here; a page gets them with useDates().
 *
 * Intl finds the day and the hour in the zone. The words are put together here
 * rather than left to the browser's locale, so they are the same English as the
 * rest of Horatio on every device.
 */
import { useMemo } from "react";
import type { Preferences } from "./api/types";
import { usePreferences } from "./hooks";

export type DateSettings = Pick<Preferences, "time_zone" | "date_format" | "clock">;

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The zone this device is set to, such as "America/New_York". */
export function deviceZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

// Making a DateTimeFormat is slow next to using one, and a log shows hundreds.
const formats = new Map<string, Intl.DateTimeFormat>();
function format(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${locale} ${JSON.stringify(options)}`;
  let made = formats.get(key);
  if (!made) formats.set(key, (made = new Intl.DateTimeFormat(locale, options)));
  return made;
}

type Day = { year: number; month: number; day: number };
type Parts = Day & { hour: number; minute: number };

/** The calendar day and the clock at a moment, in a zone. */
function partsIn(at: Date, zone: string): Parts {
  const parts = format("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(at);
  const n = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return { year: n("year"), month: n("month"), day: n("day"), hour: n("hour") % 24, minute: n("minute") };
}

// No one English locale abbreviates every zone; each falls back to "GMT+2" for
// the zones it doesn't. en-US knows "EDT", en-CA "NDT" and "IST", en-GB "BST"
// and "CEST", en-AU "AEDT" and "NZDT", en-ZA "SAST".
const NAMERS = ["en-US", "en-CA", "en-GB", "en-AU", "en-ZA"];

/** The zone's abbreviation at a moment, "EDT", or its offset, "GMT+9", where it has none. */
export function zoneName(at: Date, zone: string): string {
  let offset = "";
  for (const locale of NAMERS) {
    const name = format(locale, { timeZone: zone, timeZoneName: "short" })
      .formatToParts(at)
      .find((p) => p.type === "timeZoneName")?.value;
    if (!name) continue;
    if (!/^GMT[+-]/.test(name)) return name;
    offset ||= name;
  }
  return offset;
}

const pad = (n: number) => String(n).padStart(2, "0");

function dayText({ year, month, day }: Day, settings: DateSettings, withYear = true): string {
  if (settings.date_format === "iso") return `${year}-${pad(month)}-${pad(day)}`;
  if (settings.date_format === "month_day") return withYear ? `${month}/${day}/${year}` : `${month}/${day}`;
  const short = MONTHS[month - 1]!.slice(0, 3);
  return withYear ? `${day} ${short} ${year}` : `${day} ${short}`;
}

function timeText({ hour, minute }: Parts, settings: DateSettings): string {
  if (settings.clock === "24") return `${pad(hour)}:${pad(minute)}`;
  return `${hour % 12 || 12}:${pad(minute)} ${hour < 12 ? "am" : "pm"}`;
}

/** "7 pm" on the hour, "7:30 pm" otherwise; "19:00" on a 24-hour clock. */
function hourText(parts: Parts, settings: DateSettings): string {
  if (settings.clock === "12" && parts.minute === 0) return `${parts.hour % 12 || 12} ${parts.hour < 12 ? "am" : "pm"}`;
  return timeText(parts, settings);
}

function weekday({ year, month, day }: Day): string {
  return WEEKDAYS[new Date(Date.UTC(year, month - 1, day)).getUTCDay()]!;
}

/** A day the API sends as "2027-01-19": a date, not a moment, so the same day in every zone. */
function parseDay(day: string): Day {
  const [year = 0, month = 1, date = 1] = day.split("-").map(Number);
  return { year, month, day: date };
}

const moment = (at: Date | string) => (typeof at === "string" ? new Date(at) : at);

/** How far the zone's clock is ahead of UTC at a moment, in milliseconds. */
function offset(at: Date, zone: string): number {
  const p = partsIn(at, zone);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - Math.floor(at.getTime() / 60_000) * 60_000;
}

/** Dates and times written with these settings. */
export function datesFor(settings: DateSettings) {
  const zone = settings.time_zone ?? deviceZone();
  const fromInput = (value: string) => {
    const [day = "", clock = ""] = value.split("T");
    const d = parseDay(day);
    const [hour = 0, minute = 0] = clock.split(":").map(Number);
    const wall = Date.UTC(d.year, d.month - 1, d.day, hour, minute);
    // The offset at the wall time, then again at the moment that gives, which
    // settles it across a change to or from summer time.
    const first = wall - offset(new Date(wall), zone);
    return new Date(wall - offset(new Date(first), zone));
  };
  return {
    /** The zone times are shown in, such as "America/New_York". */
    zone,
    /** "20 Oct 2026", "10/20/2026" or "2026-10-20". */
    date: (at: Date | string) => dayText(partsIn(moment(at), zone), settings),
    /** "9:30 pm" or "21:30". */
    time: (at: Date | string) => timeText(partsIn(moment(at), zone), settings),
    /** "20 Oct 2026, 9:30 pm". */
    dateTime: (at: Date | string) => {
      const p = partsIn(moment(at), zone);
      return `${dayText(p, settings)}, ${timeText(p, settings)}`;
    },
    /**
     * A time that matters to everyone, such as a downtime's deadline, with the
     * weekday and the zone so players in other zones agree on it: "Fri 24 Oct,
     * 11:59 pm EDT". The year shows when it isn't this one (always, in ISO).
     */
    deadline: (at: Date | string, now: Date = new Date()) => {
      const when = moment(at);
      const p = partsIn(when, zone);
      const withYear = settings.date_format === "iso" || p.year !== partsIn(now, zone).year;
      return `${weekday(p)} ${dayText(p, settings, withYear)}, ${timeText(p, settings)} ${zoneName(when, zone)}`;
    },
    /** The day a deadline falls on, for a short note: "Sat 7 Nov" (with the year when it isn't this one). */
    dueDay: (at: Date | string, now: Date = new Date()) => {
      const p = partsIn(moment(at), zone);
      const withYear = settings.date_format === "iso" || p.year !== partsIn(now, zone).year;
      return `${weekday(p)} ${dayText(p, settings, withYear)}`;
    },
    /**
     * A game, from its start to its end, with the weekday and the zone: "Sat 14
     * Nov, 7 pm to 11:30 pm EST", or "Sat 14 Nov, 7 pm to Sun 15 Nov, 1 am EST"
     * when it ends on another day. The year shows when it isn't this one.
     */
    game: (start: Date | string, end: Date | string, now: Date = new Date()) => {
      const from = partsIn(moment(start), zone);
      const to = partsIn(moment(end), zone);
      const thisYear = partsIn(now, zone).year;
      const day = (p: Parts) => `${weekday(p)} ${dayText(p, settings, settings.date_format === "iso" || p.year !== thisYear)}`;
      const sameDay = from.year === to.year && from.month === to.month && from.day === to.day;
      const until = sameDay ? hourText(to, settings) : `${day(to)}, ${hourText(to, settings)}`;
      return `${day(from)}, ${hourText(from, settings)} to ${until} ${zoneName(moment(end), zone)}`;
    },
    /** When a game starts, with the weekday and the zone: "Sat 14 Nov, 7 pm EST". */
    gameStart: (start: Date | string, now: Date = new Date()) => {
      const p = partsIn(moment(start), zone);
      const withYear = settings.date_format === "iso" || p.year !== partsIn(now, zone).year;
      return `${weekday(p)} ${dayText(p, settings, withYear)}, ${hourText(p, settings)} ${zoneName(moment(start), zone)}`;
    },
    /** A day the API sends as "2027-01-19", as "19 Jan 2027". */
    day: (day: string) => dayText(parseDay(day), settings),
    /** A day the API sends as "2027-01-19", in full: "19 January 2027", "January 19, 2027" or "2027-01-19". */
    longDay: (day: string) => {
      const d = parseDay(day);
      if (settings.date_format === "iso") return dayText(d, settings);
      const month = MONTHS[d.month - 1];
      return settings.date_format === "month_day" ? `${month} ${d.day}, ${d.year}` : `${d.day} ${month} ${d.year}`;
    },
    /** The month of a moment: "March 2019", or "2019-03" in ISO. */
    month: (at: Date | string) => {
      const p = partsIn(moment(at), zone);
      return settings.date_format === "iso" ? `${p.year}-${pad(p.month)}` : `${MONTHS[p.month - 1]} ${p.year}`;
    },
    /** The zone's abbreviation now, or at a moment: "EDT". */
    zoneName: (at: Date | string = new Date()) => zoneName(moment(at), zone),
    /** A moment as a datetime-local input's value, "2026-10-24T23:59", on this zone's clock. */
    toInput: (at: Date | string) => {
      const p = partsIn(moment(at), zone);
      return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
    },
    /** A datetime-local input's value, read on this zone's clock, as the moment it means. */
    fromInput,
    /**
     * What a date or datetime-local input holds, written as everywhere else in
     * Horatio, for under the input (the browser draws the input itself, in its
     * own locale's order): "Tue 20 Oct 2026", or "Tue 20 Oct 2026, 9:30 pm EDT".
     * Empty while the input is.
     */
    inputText: (value: string) => {
      if (!value) return "";
      if (!value.includes("T")) {
        const d = parseDay(value);
        return `${weekday(d)} ${dayText(d, settings)}`;
      }
      const when = fromInput(value);
      const p = partsIn(when, zone);
      return `${weekday(p)} ${dayText(p, settings)}, ${timeText(p, settings)} ${zoneName(when, zone)}`;
    },
  };
}

export type Dates = ReturnType<typeof datesFor>;

/** Dates and times in the signed-in person's settings, or the defaults and this device's zone. */
export function useDates(): Dates {
  const { time_zone, date_format, clock } = usePreferences();
  return useMemo(() => datesFor({ time_zone, date_format, clock }), [time_zone, date_format, clock]);
}
