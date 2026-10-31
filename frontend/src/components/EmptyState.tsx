import type { ReactNode } from "react";

/**
 * What an empty list says, inside the card it belongs to: that there is nothing
 * yet (`title`), what will fill it and what to do next (`children`), and the
 * button or link to do it, if there is one here.
 */
export function EmptyState({ title, children, action }: { title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-1 py-2 text-sm">
      <p className="text-parchment">{title}</p>
      {children && <p className="text-mist">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/**
 * Whether a list's filters show: once it has something to filter. `count` is
 * how many the list holds before filtering (undefined while it loads); a filter
 * already set keeps them, so a filter that finds nothing can be undone.
 */
export function showFilters(count: number | undefined, filtering: boolean): boolean {
  return filtering || (count ?? 0) > 0;
}

/** A list's filters, hidden while there is nothing to filter (`showFilters`). */
export function FilterBar({ count, filtering, children }: { count: number | undefined; filtering: boolean; children: ReactNode }) {
  return showFilters(count, filtering) ? <>{children}</> : null;
}
