/** A day the API sends as "2027-01-19", read as that day wherever the reader is. */
export function longDate(day: string): string {
  const [year = 0, month = 1, date = 1] = day.split("-").map(Number);
  return new Date(year, month - 1, date).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}
