/**
 * Where a part of the user manual (docs/manual) is in the app: `manualLink("players",
 * "downtimes")` is `/help/players#downtimes`, and `manualLink()` the contents. Give
 * both as plain strings: a test (manual/links.test.ts) finds every call and fails if
 * its page or heading isn't in the manual, so renaming a heading can't silently break
 * a link to it.
 */
export function manualLink(page = "README", anchor?: string): string {
  return helpPath(page, anchor);
}

/** The same for a page and anchor worked out as the app runs, by the Help pages themselves. Not checked by the test. */
export function helpPath(page: string, anchor?: string | null): string {
  const path = page === "README" ? "/help" : `/help/${page}`;
  return anchor ? `${path}#${anchor}` : path;
}
