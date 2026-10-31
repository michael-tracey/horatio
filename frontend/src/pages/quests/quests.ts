/**
 * Quests (issue #323; MET: VTM Vol. II Issue 1, pp. 99-110): the words shown for
 * them, and the alternatives a quest requirement is built from.
 */
import type { RequirementIn } from "../../api/types";

export type Option = RequirementIn["options"][number];
export type OptionKind = Option["kind"];

/** What a requirement's alternative can be, as the builder offers them. */
export const OPTION_KINDS: { value: OptionKind; label: string }[] = [
  { value: "trait", label: "A trait at a rating" },
  { value: "aspect", label: "A clan, bloodline or sect" },
  { value: "influence", label: "Expend influence" },
  { value: "background", label: "Expend background dots" },
  { value: "status", label: "Expend a status trait" },
  { value: "pool", label: "Expend Willpower or Blood" },
  { value: "action", label: "Expend a downtime action" },
  { value: "item", label: "Lend an item" },
  { value: "text", label: "Something else, in words" },
];

export const TRAIT_KINDS: { value: string; label: string }[] = [
  { value: "skills", label: "Skill" },
  { value: "focus", label: "Attribute focus" },
  { value: "backgrounds", label: "Background" },
  { value: "merits", label: "Merit" },
  { value: "flaws", label: "Flaw" },
  { value: "disciplines", label: "Discipline" },
  { value: "power", label: "Discipline power" },
  { value: "techniques", label: "Technique" },
  { value: "rituals", label: "Ritual" },
];

/** One alternative as the builder's form holds it: every field, as typed. */
export type OptionDraft = {
  kind: OptionKind;
  category: string;
  name: string;
  rating: string;
  specialization: string;
  aspect: string;
  type: string;
  level: string;
  area: string;
  dots: string;
  pool: string;
  amount: string;
  action_kind: string;
  item: string;
  text: string;
};

export function emptyDraft(kind: OptionKind = "trait"): OptionDraft {
  return {
    kind,
    category: "skills",
    name: "",
    rating: "1",
    specialization: "",
    aspect: "clan",
    type: "elite",
    level: "1",
    area: "",
    dots: "1",
    pool: "willpower",
    amount: "1",
    action_kind: "general",
    item: "",
    text: "",
  };
}

const whole = (value: string, least: number): number | null => {
  const n = Number(value);
  return Number.isInteger(n) && n >= least ? n : null;
};

/** The alternative to send, or what is missing. */
export function optionFrom(d: OptionDraft): Option | string {
  const name = d.name.trim();
  switch (d.kind) {
    case "trait": {
      const rating = whole(d.rating, 0);
      if (!name) return "Name the trait.";
      if (rating === null) return "Give the rating as a number.";
      return { kind: "trait", category: d.category as "skills", name, rating, specialization: d.specialization.trim() };
    }
    case "aspect":
      if (!name) return "Name the clan, bloodline or sect.";
      return { kind: "aspect", aspect: d.aspect as "clan", name };
    case "influence": {
      const level = whole(d.level, 1);
      if (level === null) return "Give the level as a number.";
      return { kind: "influence", type: d.type as "elite", level, area: d.area.trim() };
    }
    case "background": {
      const dots = whole(d.dots, 1);
      if (!name) return "Name the background.";
      if (dots === null) return "Give the dots as a number.";
      return { kind: "background", name, dots };
    }
    case "status":
      return { kind: "status", name };
    case "pool": {
      const amount = whole(d.amount, 1);
      if (amount === null) return "Give the amount as a number.";
      return { kind: "pool", pool: d.pool as "willpower", amount };
    }
    case "action":
      return { kind: "action", action_kind: d.action_kind.trim() || "general" };
    case "item":
      if (!d.item.trim()) return "Say what is lent.";
      return { kind: "item", item: d.item.trim() };
    case "text":
      if (!d.text.trim()) return "Say what is needed.";
      return { kind: "text", text: d.text.trim() };
  }
}

/** All the alternatives, or the first thing missing ("Alternative 2: Name the trait."). */
export function optionsFrom(drafts: OptionDraft[]): Option[] | string {
  const found: Option[] = [];
  for (const [i, d] of drafts.entries()) {
    const option = optionFrom(d);
    if (typeof option === "string") return drafts.length > 1 ? `Alternative ${i + 1}: ${option}` : option;
    found.push(option);
  }
  return found;
}

const REQUEST_STATUS: Record<string, string> = {
  waiting: "Waiting",
  new: "New",
  working: "Being worked on",
  answered: "Answered",
  withdrawn: "Withdrawn",
};

/** A request's status as the player or staff read it. */
export function requestStatus(status: string): string {
  return REQUEST_STATUS[status] ?? status;
}

/** How staff answered, as a word. */
export function outcomeText(outcome: string | null | undefined): string {
  if (outcome === "quest") return "with a quest";
  if (outcome === "not_needed") return "not needed";
  if (outcome === "refused") return "refused";
  if (outcome === "done") return "done";
  return "";
}

const QUEST_STATUS: Record<string, string> = {
  draft: "Being built",
  active: "Under way",
  completed: "Completed",
  failed: "Failed",
  closed: "Closed",
};

export function questStatus(status: string): string {
  return QUEST_STATUS[status] ?? status;
}

const CATEGORY: Record<string, string> = { simple: "Simple", complex: "Complex", epic: "Epic" };

/** "Complex 2", as the troupe writes a quest's type; "Simple 4 · Downtime only" for one run only through downtime. */
export function questType(q: { category: string; difficulty: number; downtime_only?: boolean }): string {
  const type = `${CATEGORY[q.category] ?? q.category} ${q.difficulty}`;
  return q.downtime_only ? `${type} · Downtime only` : type;
}

/** A quest offered to a Quest action: "The Lost Journal: Complex 2 · scenario 1 of 2 · choosing it joins the party". */
export function questChoiceText(q: {
  name: string;
  category: string;
  difficulty: number;
  downtime_only: boolean;
  role: string;
  scenario?: number | null;
  scenario_count: number;
}): string {
  const parts = [questType(q)];
  if (q.scenario) parts.push(`scenario ${q.scenario} of ${q.scenario_count}`);
  if (q.role === "invited" || q.role === "offered") parts.push("choosing it joins the party");
  return `${q.name}: ${parts.join(" · ")}`;
}

/** The book's guide for a quest of this type (pp. 99-100), never a limit. */
export function guidanceText(g: { requirements: number; scenarios: number }): string {
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return `The book gives this ${plural(g.requirements, "requirement")} and ${plural(g.scenarios, "scenario")}.`;
}

const ROLES: Record<string, string> = {
  leader: "Leader",
  joined: "In the party",
  invited: "Shared with you",
  offered: "Open to join",
  left: "Left",
};

export function roleText(role: string): string {
  return ROLES[role] ?? role;
}

const OFFERS: Record<string, string> = {
  character: "For one character",
  chosen: "Offered to chosen characters",
  unlocked: "Unlocked by another quest",
  troupe: "Posted to the troupe",
};

export function offerText(offer: string): string {
  return OFFERS[offer] ?? offer;
}

/** "Scenario 2: passed". */
export function resultText(r: { number: number; result: string | null }): string {
  return `Scenario ${r.number}: ${r.result === "passed" ? "passed" : "failed"}`;
}

/** Who meets one alternative now, of the party's checks. */
export function meetsNow(checks: { name: string; meets: (boolean | null)[] }[], option: number): string[] {
  return checks.filter((c) => c.meets[option] === true).map((c) => c.name);
}
