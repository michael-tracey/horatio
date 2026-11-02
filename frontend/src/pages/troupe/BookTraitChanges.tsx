import type { BookTraitOut } from "../../api/types";
import { Card } from "../../components/ui";
import { pageText } from "./bookPage";

/**
 * The troupe's changes to book traits, for its players on the House rules tab: the
 * traits it bans, with why.
 */
export function BookTraitChanges({ changes }: { changes: BookTraitOut[] }) {
  const banned = changes.filter((c) => c.banned);
  const split = new Set(changes.map((c) => c.splat)).size > 1 || changes.some((c) => c.splat !== "vampire");
  return (
    <>
      {banned.length > 0 && (
        <Card title="Banned">
          <p className="mb-2 text-sm text-mist">Characters here can't buy or pick these. Those who already hold one keep it, for the storytellers to talk over.</p>
          <ul className="divide-y divide-ash">
            {banned.map((c) => (
              <li key={`${c.splat}/${c.category}/${c.name}`} className="flex flex-col gap-0.5 py-2.5 text-sm">
                <span className="text-parchment">
                  {c.name}
                  <span className="text-mist">
                    {" "}
                    · {c.category_name}
                    {split && ` for ${c.splat_label}`}
                    {c.page && ` ${pageText(c.page)}`}
                  </span>
                </span>
                {c.ban_reason && <span className="text-xs text-mist">{c.ban_reason}</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
