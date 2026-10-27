import { useState, type ReactNode } from "react";
import type { EquipmentItemOut } from "../../api/types";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, ErrorText } from "../../components/ui";
import { NO_EQUIPMENT } from "../character/EquipmentTab";
import {
  combatFirst,
  factsText,
  playText,
  qualityText,
} from "../troupe/equipment";
import { useEquipment } from "./useEquipment";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const GROUPS: { title: string; kinds: string[] }[] = [
  { title: "Weapons", kinds: ["melee", "ranged"] },
  { title: "Protective gear", kinds: ["protective"] },
  { title: "Other equipment", kinds: ["miscellaneous"] },
];

/**
 * The Play View's Equipment tab: what the character holds, laid out for the table,
 * weapons first, then armour, then the rest. Each item says what its qualities do in
 * play ("Fast: +3 initiative"); on a phone its card opens to each quality's full
 * effect, its special effects and its description, which a wider screen shows at
 * once. Reference only: nothing here changes a pool. A visiting character's
 * equipment shows wherever it plays.
 */
export function EquipmentTab({
  characterId,
  actions,
}: {
  characterId: string;
  actions?: (item: EquipmentItemOut) => ReactNode;
}) {
  const { equipment, error } = useEquipment(characterId);
  if (!equipment)
    return error ? (
      <ErrorText error={error} />
    ) : (
      <p className="py-8 text-center text-mist">Loading…</p>
    );
  if (equipment.items.length === 0)
    return <p className="py-8 text-center text-mist">{NO_EQUIPMENT}</p>;
  const items = combatFirst(equipment.items);
  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((g) => {
        const shown = items.filter((i) => g.kinds.includes(i.kind));
        if (shown.length === 0) return null;
        return (
          <section key={g.title} aria-label={g.title}>
            <h2 className="mb-2 text-base text-gold">{g.title}</h2>
            <ul className="grid items-start gap-3 md:grid-cols-2">
              {shown.map((item) => (
                <ItemCard key={item.id} item={item} actions={actions?.(item)} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

/** One item: its facts and what each quality does in play; on a phone, a tap opens the rest. */
function ItemCard({
  item,
  actions,
}: {
  item: EquipmentItemOut;
  actions?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const facts = factsText(item.facts);
  const more =
    item.qualities.some((q) => q.effect) ||
    item.effects.some((e) => e.effect) ||
    !!item.description;
  return (
    <li
      aria-label={item.name}
      className="rounded-lg border border-ash bg-dusk p-3 text-sm"
    >
      <button
        type="button"
        aria-expanded={open}
        disabled={!more}
        onClick={() => setOpen(!open)}
        className="flex w-full flex-col gap-1 text-left md:pointer-events-none"
      >
        <span className="flex w-full flex-wrap items-baseline justify-between gap-2">
          <span className="text-base font-medium text-parchment">
            {item.name}
          </span>
          <span className="flex items-center gap-2">
            {item.special && <Badge tone="gold">Special</Badge>}
            {more && (
              <span aria-hidden className="text-xs text-mist md:hidden">
                {open ? "Less ▴" : "More ▾"}
              </span>
            )}
          </span>
        </span>
        <span className="text-xs text-mist">
          {item.kind_name}
          {facts && ` · ${facts}`}
        </span>
        {item.qualities.length > 0 && (
          <span className="mt-1 flex flex-col gap-0.5">
            {item.qualities.map((q, i) => (
              <span key={`${q.name}/${i}`} className="text-parchment">
                {playText(q)}
              </span>
            ))}
          </span>
        )}
        {item.effects.length > 0 && (
          <span className="flex flex-col gap-0.5">
            {item.effects.map((e) => (
              <span key={e.name} className="text-gold">
                ★ {e.name}
              </span>
            ))}
          </span>
        )}
      </button>
      {more && (
        <div
          className={cx(
            "mt-2 flex-col gap-1.5 border-t border-ash/60 pt-2 text-xs text-mist md:flex",
            open ? "flex" : "hidden",
          )}
        >
          {item.qualities
            .filter((q) => q.effect)
            .map((q, i) => (
              <p key={`${q.name}/${i}`}>
                <span className="text-parchment">{qualityText(q)}:</span>{" "}
                {q.effect}
                {pageLabel(q.page) && (
                  <span className="whitespace-nowrap">
                    {" "}
                    ({pageLabel(q.page)})
                  </span>
                )}
              </p>
            ))}
          {item.effects.map((e) => (
            <p key={e.name}>
              <span className="text-gold">★ {e.name}:</span> {e.effect}
              {item.special_troupe_name && (
                <span> ({item.special_troupe_name}'s own)</span>
              )}
            </p>
          ))}
          {item.description && (
            <p className="whitespace-pre-line text-parchment/90">
              {item.description}
            </p>
          )}
        </div>
      )}
      {actions}
    </li>
  );
}
