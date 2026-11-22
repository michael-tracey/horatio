import type { NotificationOut } from "../api/types";

/**
 * Similar unread messages in the bell gather into one row (#1196): "3 new blog articles",
 * "2 downtimes answered". Each rule says which kinds gather (a kind, or "boon.*" for every
 * kind under boon) and how the row reads. Messages gather by rule and by troupe, so two
 * troupes' announcements are two rows, but for a rule whose every notice is about a troupe of
 * its own (`anyTroupe`). Kinds no rule names, such as word about your
 * account's safety, always show one by one, and so do tasks and messages already read.
 */
const RULES: { kinds: string[]; label: (count: number) => string; anyTroupe?: boolean }[] = [
  { kinds: ["blog.new"], label: (n) => `${n} new blog articles` },
  { kinds: ["downtime.delivered"], label: (n) => `${n} downtimes answered` },
  { kinds: ["downtime.reminder"], label: (n) => `${n} downtime reminders` },
  { kinds: ["announcement.published"], label: (n) => `${n} new announcements` },
  { kinds: ["news.published"], label: (n) => `${n} new stories` },
  { kinds: ["equipment.*"], label: (n) => `${n} changes to your equipment` },
  { kinds: ["play.*"], label: (n) => `${n} notices of powers used in play` },
  { kinds: ["sheet.bond"], label: (n) => `${n} notices of blood bonds` },
  { kinds: ["boon.*"], label: (n) => `${n} notices of boons` },
  { kinds: ["quest.*"], label: (n) => `${n} quest updates` },
  { kinds: ["project.*"], label: (n) => `${n} project updates` },
  { kinds: ["title.*"], label: (n) => `${n} titles chosen` },
  { kinds: ["character.renamed"], label: (n) => `${n} characters renamed` },
  { kinds: ["setting.changed"], label: (n) => `${n} setting changes` },
  {
    kinds: ["nominations.*"],
    label: (n) => `${n} notices of Player Nominations`,
  },
  {
    kinds: ["troupe_request.approved"],
    label: (n) => `${n} new troupes ready`,
    // Each is about a troupe of its own.
    anyTroupe: true,
  },
  { kinds: ["account.signed_up"], label: (n) => `${n} people signed up` },
];

export type NoticeRow =
  | { group: false; item: NotificationOut }
  | {
      group: true;
      /** The rule and troupe: the same from one look at the bell to the next. */
      key: string;
      label: string;
      /** Newest first, as the bell lists them. */
      items: NotificationOut[];
    };

function covers(kinds: string[], kind: string): boolean {
  return kinds.some((k) => (k.endsWith(".*") ? kind.startsWith(k.slice(0, -1)) : k === kind));
}

/** Which rule an item gathers under, and with what: none for one shown on its own. */
export function groupKey(item: NotificationOut): string | null {
  if (item.task || item.read) return null;
  const rule = RULES.findIndex((r) => covers(r.kinds, item.kind));
  if (rule < 0) return null;
  return `${rule}:${RULES[rule]!.anyTroupe ? "" : (item.troupe_id ?? "")}`;
}

/**
 * The bell's messages as rows: each that gathers with another, together in one row where
 * the newest of them is; the rest as they are, in their order.
 */
export function groupNotices(items: NotificationOut[]): NoticeRow[] {
  const keys = items.map(groupKey);
  const counts = new Map<string, number>();
  for (const key of keys) if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  const rows: NoticeRow[] = [];
  const placed = new Map<string, NotificationOut[]>();
  items.forEach((item, i) => {
    const key = keys[i];
    if (!key || counts.get(key)! < 2) return rows.push({ group: false, item });
    const gathered = placed.get(key);
    if (gathered) return gathered.push(item);
    const members = [item];
    placed.set(key, members);
    rows.push({
      group: true,
      key,
      label: RULES[Number(key.split(":")[0])]!.label(counts.get(key)!),
      items: members,
    });
  });
  return rows;
}
