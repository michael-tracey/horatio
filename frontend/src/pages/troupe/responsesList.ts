import type { WorkItemOut } from "../../api/types";

type Item = Pick<WorkItemOut, "id" | "character_id" | "character_name" | "question" | "status" | "assigned_to_user_id" | "assigned_to_any_narrator">;

export type Status = "all" | "unassigned" | "assigned" | "written";

/** Who a response is with: "none", "any" (any narrator) or a staff member's id. */
export function assigneeOf(item: Item): string {
  if (item.assigned_to_any_narrator) return "any";
  return item.assigned_to_user_id ?? "none";
}

export type ResponseFilter = { status: Status; assignee: string; question: string };

/** Whether a response shows under the filter; an empty assignee or question means any. */
export function shows(item: Item, filter: ResponseFilter): boolean {
  return (
    (filter.status === "all" || item.status === filter.status) &&
    (!filter.assignee || assigneeOf(item) === filter.assignee) &&
    (!filter.question || item.question === filter.question)
  );
}

/** The questions the responses answer, each once, in the order they first come. */
export function questionsOf(items: Item[]): string[] {
  return [...new Set(items.map((i) => i.question))];
}

export type CharacterGroup<T extends Item> = { characterId: string; name: string; items: T[] };

/** Responses by character, in the order they come (the server sorts them by name). */
export function byCharacter<T extends Item>(items: T[]): CharacterGroup<T>[] {
  const groups = new Map<string, CharacterGroup<T>>();
  for (const item of items) {
    let group = groups.get(item.character_id);
    if (!group) {
      group = { characterId: item.character_id, name: item.character_name, items: [] };
      groups.set(item.character_id, group);
    }
    group.items.push(item);
  }
  return [...groups.values()];
}

/** "3 responses", "1 response". */
export const responsesCount = (n: number) => (n === 1 ? "1 response" : `${n} responses`);
