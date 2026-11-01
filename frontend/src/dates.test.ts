import { afterEach, describe, expect, it } from "vitest";
import { datesFor, deviceZone, type DateSettings } from "./dates";

const newYork: DateSettings = { time_zone: "America/New_York", date_format: "day_month", clock: "12" };
// 9:30 pm in New York on Tuesday 20 October 2026, the next morning in Tokyo.
const at = "2026-10-21T01:30:00Z";

describe("dates", () => {
  it("writes each date format", () => {
    expect(datesFor(newYork).date(at)).toBe("20 Oct 2026");
    expect(datesFor({ ...newYork, date_format: "month_day" }).date(at)).toBe("10/20/2026");
    expect(datesFor({ ...newYork, date_format: "iso" }).date(at)).toBe("2026-10-20");
  });

  it("keeps a 12- or 24-hour clock", () => {
    expect(datesFor(newYork).time(at)).toBe("9:30 pm");
    expect(datesFor({ ...newYork, clock: "24" }).time(at)).toBe("21:30");
    expect(datesFor(newYork).time("2026-10-20T04:05:00Z")).toBe("12:05 am");
    expect(datesFor({ ...newYork, clock: "24" }).time("2026-10-20T04:05:00Z")).toBe("00:05");
    expect(datesFor(newYork).time("2026-10-20T16:00:00Z")).toBe("12:00 pm");
    expect(datesFor(newYork).dateTime(at)).toBe("20 Oct 2026, 9:30 pm");
    expect(datesFor({ ...newYork, date_format: "iso", clock: "24" }).dateTime(at)).toBe("2026-10-20, 21:30");
  });

  it("shows the moment in the chosen zone", () => {
    const tokyo = datesFor({ ...newYork, time_zone: "Asia/Tokyo" });
    expect(tokyo.dateTime(at)).toBe("21 Oct 2026, 10:30 am");
    expect(tokyo.zone).toBe("Asia/Tokyo");
  });

  describe("with no zone chosen", () => {
    const before = process.env.TZ;
    afterEach(() => {
      process.env.TZ = before;
    });

    it("follows the device's", () => {
      process.env.TZ = "Asia/Tokyo";
      expect(deviceZone()).toBe("Asia/Tokyo");
      const device = datesFor({ ...newYork, time_zone: null });
      expect(device.zone).toBe("Asia/Tokyo");
      expect(device.dateTime(at)).toBe("21 Oct 2026, 10:30 am");
      // A zone chosen wins over the device's.
      expect(datesFor(newYork).dateTime(at)).toBe("20 Oct 2026, 9:30 pm");
    });
  });

  it("writes a game's start and end, in each zone", () => {
    const now = new Date("2026-10-20T12:00:00Z");
    // 7 pm to 11:30 pm in New York on Saturday 14 November.
    const start = "2026-11-15T00:00:00Z";
    const end = "2026-11-15T04:30:00Z";
    expect(datesFor(newYork).gameStart(start, now)).toBe("Sat 14 Nov, 7 pm EST");
    expect(datesFor(newYork).game(start, end, now)).toBe("Sat 14 Nov, 7 pm to 11:30 pm EST");
    expect(datesFor({ ...newYork, clock: "24" }).game(start, end, now)).toBe("Sat 14 Nov, 19:00 to 23:30 EST");
    // In London it is the small hours of Sunday.
    expect(datesFor({ ...newYork, time_zone: "Europe/London" }).game(start, end, now)).toBe("Sun 15 Nov, 12 am to 4:30 am GMT");
    expect(datesFor({ ...newYork, time_zone: "America/Los_Angeles" }).game(start, end, now)).toBe("Sat 14 Nov, 4 pm to 8:30 pm PST");
    expect(datesFor(newYork).game(start, "2026-11-15T06:00:00Z", now)).toBe("Sat 14 Nov, 7 pm to Sun 15 Nov, 1 am EST");
    // Next year's shows its year.
    expect(datesFor(newYork).gameStart("2027-01-10T00:00:00Z", now)).toBe("Sat 9 Jan 2027, 7 pm EST");
  });

  it("writes the day a deadline falls on, in the reader's zone", () => {
    const now = new Date("2026-10-20T12:00:00Z");
    const due = "2026-10-24T03:59:00Z";
    expect(datesFor(newYork).dueDay(due, now)).toBe("Fri 23 Oct");
    expect(datesFor({ ...newYork, time_zone: "Europe/London" }).dueDay(due, now)).toBe("Sat 24 Oct");
    expect(datesFor({ ...newYork, date_format: "month_day" }).dueDay(due, now)).toBe("Fri 10/23");
    expect(datesFor(newYork).dueDay("2027-01-09T04:59:00Z", now)).toBe("Fri 8 Jan 2027");
  });

  it("writes a deadline with its weekday and zone", () => {
    const now = new Date("2026-10-20T12:00:00Z");
    const due = "2026-10-24T03:59:00Z";
    expect(datesFor(newYork).deadline(due, now)).toBe("Fri 23 Oct, 11:59 pm EDT");
    expect(datesFor({ ...newYork, date_format: "month_day", clock: "24" }).deadline(due, now)).toBe("Fri 10/23, 23:59 EDT");
    expect(datesFor({ ...newYork, date_format: "iso" }).deadline(due, now)).toBe("Fri 2026-10-23, 11:59 pm EDT");
    // In winter it is EST, and next year's shows its year.
    expect(datesFor(newYork).deadline("2027-01-09T04:59:00Z", now)).toBe("Fri 8 Jan 2027, 11:59 pm EST");
    // The same moment, as a player in London and one in Sydney read it.
    expect(datesFor({ ...newYork, time_zone: "Europe/London" }).deadline(due, now)).toBe("Sat 24 Oct, 4:59 am BST");
    expect(datesFor({ ...newYork, time_zone: "Europe/Paris", clock: "24" }).deadline(due, now)).toBe("Sat 24 Oct, 05:59 CEST");
    expect(datesFor({ ...newYork, time_zone: "Australia/Sydney" }).deadline(due, now)).toBe("Sat 24 Oct, 2:59 pm AEDT");
    // A zone with no English abbreviation shows its offset.
    expect(datesFor({ ...newYork, time_zone: "Asia/Tokyo" }).deadline(due, now)).toBe("Sat 24 Oct, 12:59 pm GMT+9");
    expect(datesFor({ ...newYork, time_zone: "UTC" }).deadline(due, now)).toBe("Sat 24 Oct, 3:59 am UTC");
  });

  it("reads a day as that day in every zone", () => {
    for (const time_zone of ["Pacific/Honolulu", "Pacific/Kiritimati", null]) {
      expect(datesFor({ ...newYork, time_zone }).day("2027-01-19")).toBe("19 Jan 2027");
      expect(datesFor({ ...newYork, time_zone }).longDay("2027-01-19")).toBe("19 January 2027");
    }
    expect(datesFor({ ...newYork, date_format: "month_day" }).longDay("2027-01-19")).toBe("January 19, 2027");
    expect(datesFor({ ...newYork, date_format: "iso" }).longDay("2027-01-19")).toBe("2027-01-19");
    expect(datesFor({ ...newYork, date_format: "iso" }).day("2027-01-09")).toBe("2027-01-09");
  });

  it("writes a month", () => {
    expect(datesFor(newYork).month("2019-03-04T12:00:00Z")).toBe("March 2019");
    expect(datesFor({ ...newYork, date_format: "iso" }).month("2019-03-04T12:00:00Z")).toBe("2019-03");
  });

  it("fills and reads a datetime input on the zone's clock", () => {
    const dates = datesFor(newYork);
    expect(dates.toInput(at)).toBe("2026-10-20T21:30");
    expect(dates.fromInput("2026-10-20T21:30").toISOString()).toBe("2026-10-21T01:30:00.000Z");
    expect(datesFor({ ...newYork, time_zone: "Asia/Tokyo" }).fromInput("2026-10-21T10:30").toISOString()).toBe("2026-10-21T01:30:00.000Z");
    // Either side of the change from summer time.
    expect(dates.fromInput("2026-11-01T00:30").toISOString()).toBe("2026-11-01T04:30:00.000Z");
    expect(dates.fromInput("2026-11-01T12:00").toISOString()).toBe("2026-11-01T17:00:00.000Z");
    expect(dates.fromInput("2026-03-08T12:00").toISOString()).toBe("2026-03-08T16:00:00.000Z");
  });
});
