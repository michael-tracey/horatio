import type { BookTraitOut } from "../../api/types";
import { HouseWording } from "../../components/TroupeChange";
import { Card } from "../../components/ui";
import { pageText } from "./bookPage";

/**
 * The troupe's changes to book traits, for its players on the House rules tab: the
 * traits it bans, with why, those it gives wording of its own, and the merits and
 * flaws it puts in another category.
 */
export function BookTraitChanges({ changes }: { changes: BookTraitOut[] }) {
  const banned = changes.filter((c) => c.banned);
  const worded = changes.filter((c) => c.wording);
  const moved = changes.filter((c) => c.kind);
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
      {worded.length > 0 && (
        <Card title="Changed wording">
          <p className="mb-2 text-sm text-mist">The troupe's own words for these traits, which players see wherever they read them.</p>
          <ul className="divide-y divide-ash">
            {worded.map((c) => (
              <li key={`${c.splat}/${c.category}/${c.name}`} className="flex flex-col gap-1 py-2.5 text-sm">
                <span className="text-parchment">
                  {c.name}
                  <span className="text-mist">
                    {" "}
                    · {c.category_name}
                    {split && ` for ${c.splat_label}`}
                    {c.page && ` ${pageText(c.page)}`}
                  </span>
                </span>
                <HouseWording change={c} />
              </li>
            ))}
          </ul>
        </Card>
      )}
      {moved.length > 0 && (
        <Card title="Changed categories">
          <p className="mb-2 text-sm text-mist">These merits and flaws are in another category here, and every rule tied to the category follows it.</p>
          <ul className="divide-y divide-ash">
            {moved.map((c) => (
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
                <span className="text-xs text-mist">
                  {c.kind} here; {c.book_kind ?? "another category"} in the book.
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
