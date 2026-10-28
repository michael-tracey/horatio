import { useState } from "react";
import type { PlayItem, TestPool } from "../../api/types";
import { combatFirst } from "../troupe/equipment";
import { displaced, equipKey, equipmentModifiers, LIMITS } from "./equipped";
import { describe } from "./pools";
import type { makeTap } from "./tracker";

type Tap = (what: Parameters<typeof makeTap>[0]) => void;

const GROUPS: { title: string; kinds: string[]; limit: string }[] = [
  { title: "Weapons", kinds: ["melee", "ranged"], limit: LIMITS.weapons! },
  { title: "Protective gear", kinds: ["protective"], limit: LIMITS.protective! },
  { title: "Other equipment", kinds: ["miscellaneous"], limit: LIMITS.miscellaneous! },
];

const sentence = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;

/**
 * "Equipment": the items the character holds, each with an Equipped switch (issue
 * #306). While an item is equipped, its qualities' pool effects count as modifiers,
 * as the player's own do. Equipping one that doesn't fit puts away what it would
 * replace, and says so. A tap, logged with Undo, that works with no signal.
 */
export function EquipmentSwitches({ items, equipped, pools, tap }: { items: PlayItem[]; equipped: string[]; pools: TestPool[]; tap: Tap }) {
  const [moved, setMoved] = useState<string | null>(null);
  if (items.length === 0) return null;
  const counted = new Set(equipmentModifiers(items, equipped).map((m) => m.id));
  const toggle = (item: PlayItem, on: boolean) => {
    const gone = on ? displaced({ equipment: items, equipped }, item) : [];
    setMoved(gone.length ? gone.map((g) => sentence(g.said)).join(" ") : null);
    tap({ kind: "change", tracker: equipKey(item.id), amount: on ? 1 : -1 });
  };
  return (
    <div className="border-t border-ash pt-2" role="group" aria-label="Equipment">
      <h3 className="text-xs tracking-wide text-mist uppercase">Equipment</h3>
      <p aria-live="polite" className="mt-1 text-sm text-gold empty:hidden">
        {moved}
      </p>
      {GROUPS.map((g) => {
        const shown = combatFirst(items.filter((i) => g.kinds.includes(i.kind)));
        if (shown.length === 0) return null;
        return (
          <div key={g.title} className="mt-1">
            <p className="text-xs text-mist">
              {g.title}: {g.limit}
            </p>
            <ul className="divide-y divide-ash/60" aria-label={g.title}>
              {shown.map((item) => {
                const on = equipped.includes(item.id);
                return (
                  <li key={item.id} className="py-2">
                    <label className="flex min-h-10 items-start gap-3">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-5 w-5 shrink-0 accent-[var(--color-gold)]"
                        checked={on}
                        onChange={(e) => toggle(item, e.target.checked)}
                        aria-label={`${item.name} equipped`}
                      />
                      <span className="min-w-0">
                        <span className={on ? "text-parchment" : "text-mist"}>{item.name}</span>
                        {item.hands === 2 && <span className="text-xs text-mist"> · two hands</span>}
                        {item.modifiers.length === 0 && <span className="block text-xs text-mist">Changes no pool.</span>}
                        {item.modifiers.map((m, at) => (
                          <span key={`${m.quality}/${at}`} className={`block text-xs ${on ? "text-parchment/80" : "text-mist"}`}>
                            {m.quality}: {describe(m, pools)}
                            {on && !counted.has(`${item.id}/${at}`) && " (counted once, from the other weapon: p. 248)"}
                          </span>
                        ))}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
