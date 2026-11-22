import { describe, expect, it } from "vitest";
import type { NotificationOut } from "../api/types";
import { groupKey, groupNotices } from "./noticeGroups";

let made = 0;
function notice(kind: string, more: Partial<NotificationOut> = {}): NotificationOut {
  made += 1;
  return {
    id: `n${made}`,
    kind,
    task: false,
    troupe_id: "t1",
    troupe_name: "Lords of the Night",
    summary: `${kind} ${made}`,
    link: "/",
    at: new Date(Date.UTC(2026, 10, 22, 12, 0) - made * 60_000).toISOString(),
    read: false,
    picture: null,
    player_id: null,
    player_name: null,
    ...more,
  };
}

const shape = (rows: ReturnType<typeof groupNotices>) => rows.map((r) => (r.group ? `${r.label}: ${r.items.map((i) => i.id).join(" ")}` : r.item.id));

describe("gathering the bell's messages (#1196)", () => {
  it("gathers similar unread messages into one row where the newest is, and leaves the rest as they are", () => {
    const blog = [notice("blog.new", { troupe_id: null, troupe_name: null }), notice("blog.new", { troupe_id: null, troupe_name: null })];
    const renamed = notice("character.renamed");
    const results = [notice("downtime.delivered"), notice("downtime.delivered"), notice("downtime.delivered")];
    const lateBlog = notice("blog.new", { troupe_id: null, troupe_name: null });
    const rows = groupNotices([blog[0]!, renamed, results[0]!, blog[1]!, results[1]!, results[2]!, lateBlog]);
    expect(shape(rows)).toEqual([`3 new blog articles: ${blog[0]!.id} ${blog[1]!.id} ${lateBlog.id}`, renamed.id, `3 downtimes answered: ${results.map((r) => r.id).join(" ")}`]);
  });

  it("gathers by troupe, and kinds under one rule together", () => {
    const here = [notice("boon.accepted"), notice("boon.traded")];
    const there = [notice("boon.accepted", { troupe_id: "t2", troupe_name: "Court of Ashes" }), notice("boon.rejected", { troupe_id: "t2", troupe_name: "Court of Ashes" })];
    expect(shape(groupNotices([here[0]!, there[0]!, here[1]!, there[1]!]))).toEqual([`2 notices of boons: ${here[0]!.id} ${here[1]!.id}`, `2 notices of boons: ${there[0]!.id} ${there[1]!.id}`]);
    expect(groupKey(here[0]!)).not.toEqual(groupKey(there[0]!));
  });

  it("gathers new troupes across troupes, as each is a troupe of its own", () => {
    const ready = [notice("troupe_request.approved", { troupe_id: "t3" }), notice("troupe_request.approved", { troupe_id: "t4" })];
    expect(shape(groupNotices(ready))).toEqual([`2 new troupes ready: ${ready[0]!.id} ${ready[1]!.id}`]);
  });

  it("leaves one of a kind, read messages, tasks and word about the account's safety one by one", () => {
    const items = [
      notice("announcement.published"),
      notice("announcement.published", { read: true }),
      notice("teaching", { task: true }),
      notice("teaching", { task: true }),
      notice("account.two_step_reset", { troupe_id: null }),
      notice("account.two_step_reset", { troupe_id: null }),
    ];
    expect(shape(groupNotices(items))).toEqual(items.map((i) => i.id));
    expect(items.map(groupKey)).toEqual([expect.any(String), null, null, null, null, null]);
  });
});
