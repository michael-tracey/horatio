import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useNavigate, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { QuestIn, QuestRequestOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, PageTabs, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { guidanceText, offerText, outcomeText, questStatus, questType, requestStatus } from "../quests/quests";
import { QuestPage } from "./QuestPage";

type Show = "open" | "new" | "mine" | "any_narrator" | "to_send" | "answered";
const SHOWS: { value: Show; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "new", label: "New" },
  { value: "mine", label: "Assigned to me" },
  { value: "any_narrator", label: "Any narrator" },
  { value: "to_send", label: "Waiting to send" },
  { value: "answered", label: "Answered" },
];

/**
 * The troupe's quests, for its staff: the queue of quest requests, the quests
 * themselves, and building one. Narrators see what is assigned to them.
 */
export function QuestsTab({ troupeId, running }: { troupeId: string; running: boolean }) {
  const base = `/troupes/${troupeId}/quests`;
  return (
    <>
      <PageTabs
        label="Quests"
        tabs={[
          { to: base, label: "Requests", end: true },
          { to: `${base}/all`, label: "Quests" },
          ...(running ? [{ to: `${base}/new`, label: "New quest" }] : []),
        ]}
      />
      <Routes>
        <Route index element={<Requests troupeId={troupeId} running={running} />} />
        <Route path="all" element={<QuestList troupeId={troupeId} />} />
        <Route path="new" element={<NewQuest troupeId={troupeId} />} />
        <Route path=":questId" element={<QuestPage troupeId={troupeId} />} />
      </Routes>
    </>
  );
}

function Requests({ troupeId, running }: { troupeId: string; running: boolean }) {
  const [show, setShow] = useState<Show>("open");
  const requests = useQuery({
    queryKey: ["quest-requests", troupeId, show],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-requests", { params: { path: { troupe_id: troupeId }, query: { show } } })),
  });
  const staff = useQuery({
    queryKey: ["staff", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", { params: { path: { troupe_id: troupeId } } })),
    enabled: running,
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Show requests">
        {SHOWS.map((s) => (
          <Button key={s.value} variant={s.value === show ? "secondary" : "ghost"} aria-pressed={s.value === show} onClick={() => setShow(s.value)}>
            {s.label}
          </Button>
        ))}
      </div>
      {requests.isPending ? (
        <Loading />
      ) : requests.error ? (
        <ErrorText error={requests.error} />
      ) : requests.data.length === 0 ? (
        <Empty>No quest requests here.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {requests.data.map((r) => (
            <RequestCard key={r.id} request={r} troupeId={troupeId} staff={staff.data ?? []} />
          ))}
        </ul>
      )}
    </div>
  );
}

function RequestCard({ request: r, troupeId, staff }: { request: QuestRequestOut; troupeId: string; staff: { user_id: string; display_name: string }[] }) {
  const dates = useDates();
  const navigate = useNavigate();
  const [answering, setAnswering] = useState<"not_needed" | "refused" | null>(null);
  const [note, setNote] = useState("");
  const path = { params: { path: { request_id: r.id } } };
  const assign = useAction((value: string) =>
    unwrap(api.PUT("/api/quest-requests/{request_id}/assignment", { ...path, body: value === "any" ? { any_narrator: true } : { any_narrator: false, user_id: value || null } })),
  );
  const accept = useAction(() => unwrap(api.POST("/api/quest-requests/{request_id}/accept", path)));
  const read = useAction(() => unwrap(api.POST("/api/quest-requests/{request_id}/read", path)));
  const answer = useAction(async (outcome: "not_needed" | "refused") => {
    await unwrap(api.POST("/api/quest-requests/{request_id}/answer", { ...path, body: { outcome, note } }));
    setAnswering(null);
  });
  const open = r.status === "new" || r.status === "working";
  const assigned = r.assigned_to_any_narrator ? "any" : (r.assigned_to_user_id ?? "");

  return (
    <li aria-label={`Request from ${r.character_name}`} className="rounded-lg border border-ash bg-dusk p-4 text-sm">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span>
          <span className="text-gold">{r.character_name}</span> <span className="text-mist">({r.player_name})</span> ·{" "}
          <time dateTime={r.created_at} className="text-mist">
            {dates.dateTime(r.created_at)}
          </time>
        </span>
        <Badge tone={r.status === "new" ? "gold" : "mist"}>
          {requestStatus(r.status)}
          {r.outcome ? `: ${outcomeText(r.outcome)}` : ""}
        </Badge>
      </div>
      <p className="whitespace-pre-line text-parchment">{r.objective}</p>
      {r.reason && <p className="mt-1 whitespace-pre-line text-mist">Why: {r.reason}</p>}
      {r.companions && <p className="mt-1 text-mist">Would bring: {r.companions}</p>}
      {r.note && <p className="mt-1">Answer: {r.note}</p>}
      <p className="mt-2 text-xs text-mist">
        {r.assigned_to_any_narrator ? "Assigned to any narrator" : r.assigned_to_name ? `Assigned to ${r.assigned_to_name}` : "Not assigned"}
        {r.read_by.length > 0 && ` · Read by ${r.read_by.join(", ")}`}
        {r.quest_id && (
          <>
            {" · "}
            <Link to={`/troupes/${troupeId}/quests/${r.quest_id}`} className="text-gold hover:text-parchment">
              {r.quest_name}
            </Link>{" "}
            ({questStatus(r.quest_status ?? "")})
          </>
        )}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {r.can_assign && (
          <Select aria-label={`Assign ${r.character_name}'s request to`} className="w-auto" value={assigned} onChange={(e) => assign.mutate(e.target.value)}>
            <option value="">Unassigned</option>
            <option value="any">Any narrator</option>
            {staff.map((s) => (
              <option key={s.user_id} value={s.user_id}>
                {s.display_name}
              </option>
            ))}
          </Select>
        )}
        {open && r.assigned_to_any_narrator && !r.can_assign && (
          <Button variant="secondary" onClick={() => accept.mutate(undefined)}>
            Accept
          </Button>
        )}
        {r.can_work && !r.quest_id && (
          <>
            <Button onClick={() => navigate(`/troupes/${troupeId}/quests/new?request=${r.id}`)}>Build a quest</Button>
            <Button variant="secondary" onClick={() => setAnswering("not_needed")}>
              Not needed
            </Button>
            <Button variant="danger" onClick={() => setAnswering("refused")}>
              Refuse
            </Button>
          </>
        )}
        <Button variant="ghost" onClick={() => read.mutate(undefined)}>
          Mark read
        </Button>
      </div>
      {answering && (
        <form
          className="mt-3 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            answer.mutate(answering);
          }}
        >
          <Field label={answering === "not_needed" ? "Why it isn't needed" : "Why it is refused"}>
            <Textarea rows={2} required value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={answer.isPending}>
              {answering === "not_needed" ? "Answer: not needed" : "Refuse it"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setAnswering(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      <ErrorText error={assign.error ?? accept.error ?? answer.error ?? read.error} />
    </li>
  );
}

function QuestList({ troupeId }: { troupeId: string }) {
  const [show, setShow] = useState<"open" | "ended" | "closed" | "all">("open");
  const found = useQuery({
    queryKey: ["troupe-quests", troupeId, show],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quests", { params: { path: { troupe_id: troupeId }, query: { show } } })),
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Show quests">
        {(
          [
            ["open", "Being built and under way"],
            ["ended", "Ended"],
            ["closed", "Closed"],
            ["all", "All"],
          ] as const
        ).map(([value, label]) => (
          <Button key={value} variant={value === show ? "secondary" : "ghost"} aria-pressed={value === show} onClick={() => setShow(value)}>
            {label}
          </Button>
        ))}
      </div>
      {found.isPending ? (
        <Loading />
      ) : found.error ? (
        <ErrorText error={found.error} />
      ) : found.data.length === 0 ? (
        <Empty>No quests here.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {found.data.map((q) => (
            <li key={q.id} className="rounded-md border border-ash bg-dusk p-3 text-sm">
              <Link to={`/troupes/${troupeId}/quests/${q.id}`} className="text-gold hover:text-parchment">
                {q.name}
              </Link>{" "}
              <span className="text-mist">
                · {questType(q)} · {questStatus(q.status)} · {q.leader_name ? `for ${q.leader_name}` : offerText(q.offer)}
                {q.assigned_to_any_narrator ? " · any narrator" : q.assigned_to_name ? ` · ${q.assigned_to_name}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The fields a quest is built with, as typed. */
export type QuestDraft = Omit<QuestIn, "scenarios" | "request_id">;

export function QuestFields({
  troupeId,
  draft,
  onChange,
  fromRequest,
}: {
  troupeId: string;
  draft: QuestDraft;
  onChange: (change: Partial<QuestDraft>) => void;
  fromRequest?: boolean;
}) {
  const characters = useQuery({
    queryKey: ["quest-characters", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-characters", { params: { path: { troupe_id: troupeId } } })),
  });
  const others = useQuery({
    queryKey: ["troupe-quests", troupeId, "all"],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quests", { params: { path: { troupe_id: troupeId }, query: { show: "all" } } })),
    enabled: draft.offer === "unlocked",
  });
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Quest name">
        <Input required value={draft.name} onChange={(e) => onChange({ name: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Category">
          <Select value={draft.category} onChange={(e) => onChange({ category: e.target.value as QuestDraft["category"] })}>
            <option value="simple">Simple</option>
            <option value="complex">Complex</option>
            <option value="epic">Epic</option>
          </Select>
        </Field>
        <Field label="Difficulty">
          <Select value={draft.difficulty} onChange={(e) => onChange({ difficulty: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="Objective">
          <Textarea rows={3} value={draft.objective} onChange={(e) => onChange({ objective: e.target.value })} />
        </Field>
      </div>
      {!fromRequest && (
        <Field label="Leader">
          <Select value={draft.leader_id ?? ""} onChange={(e) => onChange({ leader_id: e.target.value || null })}>
            <option value="">No one yet</option>
            {characters.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Field label="Who it is for">
        <Select value={draft.offer} onChange={(e) => onChange({ offer: e.target.value as QuestDraft["offer"] })}>
          {(["character", "chosen", "unlocked", "troupe"] as const).map((o) => (
            <option key={o} value={o}>
              {offerText(o)}
            </option>
          ))}
        </Select>
      </Field>
      {draft.offer === "unlocked" && (
        <>
          <Field label="Unlocked by the quest">
            <Select value={draft.unlock_quest_id ?? ""} onChange={(e) => onChange({ unlock_quest_id: e.target.value || null })}>
              <option value="">Choose a quest</option>
              {others.data?.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Its scenario">
            <Input type="number" min={1} max={20} value={draft.unlock_scenario ?? ""} onChange={(e) => onChange({ unlock_scenario: e.target.value ? Number(e.target.value) : null })} />
          </Field>
        </>
      )}
      <label className="flex min-h-10 items-center gap-2 text-sm">
        <input type="checkbox" checked={!!draft.downtime_only} onChange={(e) => onChange({ downtime_only: e.target.checked })} />
        Downtime only
      </label>
      <div className="sm:col-span-2">
        <Field label="Notes for staff only">
          <Textarea rows={2} value={draft.staff_notes} onChange={(e) => onChange({ staff_notes: e.target.value })} />
        </Field>
      </div>
    </div>
  );
}

function bookGuidance(category: string, difficulty: number): { requirements: number; scenarios: number } {
  const per: Record<string, [number, number]> = { simple: [1, 0], complex: [2, 1], epic: [3, 2] };
  const [r, s] = per[category] ?? [1, 0];
  return { requirements: r * difficulty, scenarios: Math.max(1, s * difficulty) };
}

function NewQuest({ troupeId }: { troupeId: string }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const requestId = params.get("request");
  const request = useQuery({
    queryKey: ["quest-requests", troupeId, "open"],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-requests", { params: { path: { troupe_id: troupeId }, query: { show: "open" } } })),
    enabled: !!requestId,
  });
  const from = request.data?.find((r) => r.id === requestId);
  const [draft, setDraft] = useState<QuestDraft>({
    name: "",
    objective: "",
    category: "simple",
    difficulty: 1,
    downtime_only: false,
    staff_notes: "",
    leader_id: null,
    offer: "character",
    unlock_quest_id: null,
    unlock_scenario: null,
  });
  const build = useAction(async () => {
    const made = await unwrap(
      api.POST("/api/troupes/{troupe_id}/quests", { params: { path: { troupe_id: troupeId } }, body: { ...draft, request_id: requestId } }),
    );
    navigate(`/troupes/${troupeId}/quests/${made.id}`);
  });
  if (requestId && request.isPending) return <Loading />;
  return (
    <Card title={from ? `A quest for ${from.character_name}` : "New quest"}>
      {from && (
        <p className="mb-3 text-sm text-mist">
          From the request: “{from.objective}”. Left empty, its objective is the request's words.
        </p>
      )}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          build.mutate(undefined);
        }}
      >
        <QuestFields troupeId={troupeId} draft={draft} onChange={(change) => setDraft({ ...draft, ...change })} fromRequest={!!from} />
        <p className="text-sm text-mist">{guidanceText(bookGuidance(draft.category, draft.difficulty))} Its scenarios start empty, to fill in on the quest.</p>
        <div>
          <Button type="submit" disabled={build.isPending}>
            Build the quest
          </Button>
        </div>
        <ErrorText error={build.error} />
      </form>
    </Card>
  );
}
