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
