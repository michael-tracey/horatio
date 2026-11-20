import type { ReactNode } from "react";
import type { EquipmentItemOut, PlayView } from "../../api/types";
import { Button } from "../../components/ui";
import { CarriedItems } from "./Equipment";
import { MEMBER, memberDown, memberHealth, type Damage } from "./tracker";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

type Member = PlayView["stock_members"][number];
type Change = (tracker: string, amount: number, damage?: Damage) => void;

/** What a group's members carry (#1056), each its own, and what the group carries: the items no member was given. */
export function itemsByMember(view: Pick<PlayView, "stock" | "stock_items">): { group: EquipmentItemOut[]; of: (number: number) => EquipmentItemOut[] } {
  const holder = view.stock?.item_members ?? {};
  return {
    group: view.stock_items.filter((i) => !holder[i.id]),
    of: (number) => view.stock_items.filter((i) => holder[i.id] === number),
  };
}

/**
 * A group of Stock NPCs' members (#1056) on its Scene card or Play View: a row
 * each, with its kind's resource and its health levels to tap, and what it
 * carries. A member with every level marked is struck off: out of the fight
 * (MET: VTM p. 490). Staff strike one off by hand too, fled or surrendered with
 * levels left, and bring it back (#1075). They share the stat block shown beside them.
 */
export function StockMembers({ view, change, big }: { view: PlayView; change: Change; big?: boolean }) {
  const members = view.stock_members ?? [];
  const standing = members.filter((m) => !memberDown(view, m)).length;
  const items = itemsByMember(view);
  return (
    <section aria-label="Members" className="flex flex-col gap-2">
      <p className="flex items-baseline justify-between text-sm">
        <span className="text-gold">Members</span>
        <span className="text-mist">
          {standing} of {members.length} standing
        </span>
      </p>
      <ul className={cx("grid gap-2", big && "md:grid-cols-2")}>
        {members.map((m) => (
          <MemberRow key={m.number} view={view} member={m} change={change} big={big} carries={items.of(m.number)} />
        ))}
      </ul>
      <CarriedItems items={items.group} title="The group carries" />
    </section>
  );
}

function MemberRow({ view, member, change, big, carries }: { view: PlayView; member: Member; change: Change; big?: boolean; carries: EquipmentItemOut[] }) {
  const health = `${MEMBER}${member.number}/health`;
  const blood = `${MEMBER}${member.number}/blood`;
  const struck = `${MEMBER}${member.number}/struck`;
  const total = memberHealth(view);
  const marks = member.marks;
  const down = memberDown(view, member);
  const has = (kind: Damage) => marks.includes(kind);
  const size = big ? "min-h-12" : "min-h-10 px-2";
  return (
    <li aria-label={member.name} className={cx("flex flex-col gap-1.5 rounded-md border p-2", down ? "border-blood/60 bg-night/40" : "border-ash")}>
      <p className="flex items-baseline justify-between gap-2 text-sm">
        <span className={cx(down ? "text-mist line-through" : "text-parchment")}>{member.name}</span>
        {down && <span className="text-xs text-blood-bright">Out of the fight</span>}
        <span className="ml-auto font-display text-lg" aria-label={`Health: ${marks.length} of ${total} marked`}>
          {marks.length}
          <span className="text-sm text-mist"> / {total} marked</span>
        </span>
      </p>
      <div className="flex flex-wrap gap-1" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={cx("h-2.5 w-2.5 rounded-sm border", marks[i] === "aggravated" ? "border-blood bg-blood" : marks[i] === "normal" ? "border-mist bg-mist" : "border-line bg-night")}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <Button variant="danger" className={size} disabled={marks.length >= total} onClick={() => change(health, 1, "normal")}>
          + Normal
        </Button>
        <Button variant="danger" className={size} disabled={marks.length >= total} onClick={() => change(health, 1, "aggravated")}>
          + Aggravated
        </Button>
        <Button variant="secondary" className={size} disabled={!has("normal")} onClick={() => change(health, -1, "normal")}>
          Heal normal
        </Button>
        <Button variant="secondary" className={size} disabled={!has("aggravated")} onClick={() => change(health, -1, "aggravated")}>
          Heal aggravated
        </Button>
        <Button
          variant="secondary"
          className={cx(size, "col-span-2")}
          aria-label={`${member.struck ? "Bring back" : "Strike off"} ${member.name}`}
          onClick={() => change(struck, member.struck ? -1 : 1)}
        >
          {member.struck ? "Bring back" : "Strike off"}
        </Button>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="flex-1 text-gold">{view.blood_name}</span>
        <span className="font-display text-lg" aria-label={`${view.blood_name}: ${member.blood.value} of ${member.blood.most}`}>
          {member.blood.value}
          <span className="text-sm text-mist"> / {member.blood.most}</span>
        </span>
        <Step label={`Spend ${view.blood_name}`} tone="blood" disabled={member.blood.value <= 0} onClick={() => change(blood, -1)}>
          −
        </Step>
        <Step label={`Restore ${view.blood_name}`} disabled={member.blood.value >= member.blood.most} onClick={() => change(blood, 1)}>
          +
        </Step>
      </div>
      <CarriedItems items={carries} />
    </li>
  );
}

function Step({ label, onClick, disabled, tone = "plain", children }: { label: string; onClick: () => void; disabled?: boolean; tone?: "plain" | "blood"; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "grid h-10 min-w-10 place-items-center rounded-full border px-2 text-lg font-semibold transition-colors active:scale-95 tap-off",
        tone === "blood" ? "border-blood bg-blood text-parchment hover:bg-blood-bright" : "border-line bg-night text-parchment hover:border-mist",
      )}
    >
      {children}
    </button>
  );
}
