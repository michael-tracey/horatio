/**
 * Heading anchors as GitHub makes them, so a link written for the manual on GitHub
 * works in the app too: lowercase, punctuation dropped except `-` and `_`, and each
 * space a `-`. "Spending XP & approvals" is `spending-xp--approvals`.
 */
export function slug(heading: string): string {
  return heading
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}\p{Pc}\- ]/gu, "")
    .replace(/ /g, "-");
}

/** Slugs for a page's headings in order: a repeated heading gets `-1`, `-2`… after it, as on GitHub. */
export function slugger(): (heading: string) => string {
  const seen = new Map<string, number>();
  return (heading) => {
    const base = slug(heading);
    let id = base;
    let n = seen.get(base) ?? 0;
    while (seen.has(id)) id = `${base}-${++n}`;
    seen.set(base, n);
    seen.set(id, 0);
    return id;
  };
}
