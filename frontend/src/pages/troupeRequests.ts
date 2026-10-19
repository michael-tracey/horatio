/** Words for asking the custodian for a new troupe (issue #51), shared by the
 * Troupes page and the custodian's list. */

const STATUSES: Record<string, string> = {
  pending: "Waiting",
  approved: "Approved",
  declined: "Declined",
  withdrawn: "Withdrawn",
};

export function requestStatus(status: string): string {
  return STATUSES[status] ?? status;
}

/** "19 Oct 2026": when a request was made or decided. */
export function when(at: string): string {
  return new Date(at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
