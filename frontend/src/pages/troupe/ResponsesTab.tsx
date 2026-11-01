import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CycleOut, StaffMember, WorkItemOut } from "../../api/types";
import { ResponseEditor } from "../../components/ResponseEditor";
import { useToast } from "../../components/Toast";
import { Button, Empty, ErrorText, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { roleLabel } from "./roles";
import { assigneeOf, byCharacter, questionsOf, responsesCount, shows, type ResponseFilter, type Status } from "./responsesList";

/**
 * Every response in a cycle, for storytellers and assistants to share out and
 * write: by character, each folding away, filtered by status, by who has it and
 * by question, and ticked to assign several in one go.
 */
export function ResponsesTab({ cycle }: { cycle: CycleOut }) {
  const [filter, setFilterState] = useState<ResponseFilter>({ status: "all", assignee: "", question: "" });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [folded, setFolded] = useState<Set<string>>(new Set());
  const items = useQuery({
    queryKey: ["responses", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/responses", { params: { path: { cycle_id: cycle.id } } })),
  });
  const staff = useQuery({
    queryKey: ["staff", cycle.troupe_id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", { params: { path: { troupe_id: cycle.troupe_id } } })),
  });
  if (items.isPending) return <Loading />;
  if (items.error) return <ErrorText error={items.error} />;

  // What is ticked is always among what shows: a new filter starts afresh.
  const setFilter = (next: Partial<ResponseFilter>) => {
    setFilterState({ ...filter, ...next });
    setSelected(new Set());
  };
  const all = items.data;
  const shown = all.filter((i) => shows(i, filter));
  const groups = byCharacter(shown);
  const questions = questionsOf(all);
  const members = staff.data ?? [];
  const tick = (ids: string[], on: boolean) => {
    const next = new Set(selected);
    for (const id of ids) {
      if (on) next.add(id);
      else next.delete(id);
    }
    setSelected(next);
  };
  const shownIds = shown.map((i) => i.id);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {(["all", "unassigned", "assigned", "written"] as const).map((f: Status) => (
          <Button key={f} variant={f === filter.status ? "secondary" : "ghost"} className="capitalize" onClick={() => setFilter({ status: f })}>
            {f} ({f === "all" ? all.length : all.filter((i) => i.status === f).length})
          </Button>
        ))}
      </div>
      {all.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm text-mist">
            Who has it
            <Select className="w-auto" value={filter.assignee} onChange={(e) => setFilter({ assignee: e.target.value })}>
              <option value="">Anyone</option>
              <AssigneeOptions staff={members} />
            </Select>
          </label>
          {questions.length > 1 && (
            <label className="flex flex-col gap-1 text-sm text-mist">
              Question
              <Select className="w-auto" value={filter.question} onChange={(e) => setFilter({ question: e.target.value })}>
                <option value="">Every question</option>
                {questions.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {groups.length > 1 && (
            <Button
              variant="ghost"
              onClick={() => setFolded(folded.size === groups.length ? new Set() : new Set(groups.map((g) => g.characterId)))}
            >
              {folded.size === groups.length ? "Unfold all" : "Fold all"}
            </Button>
          )}
        </div>
      )}
      {shown.length === 0 ? (
        <Empty>{all.length === 0 ? "No responses yet: they come as players submit their downtimes." : "No responses match."}</Empty>
      ) : (
        <>
          <Tick label="Select all shown" ids={shownIds} selected={selected} onChange={tick} />
          {groups.map((group) => {
            const open = !folded.has(group.characterId);
            const written = group.items.filter((i) => i.status === "written").length;
            const ids = group.items.map((i) => i.id);
            return (
              <section key={group.characterId} aria-label={group.name} className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-ash pb-1">
                  <Tick label={`Select all of ${group.name}'s`} ids={ids} selected={selected} onChange={tick} hidden />
                  <button
                    type="button"
                    aria-expanded={open}
                    className="flex min-h-10 flex-1 items-center gap-2 text-left font-medium text-gold hover:text-parchment"
                    onClick={() => {
                      const next = new Set(folded);
                      if (!next.delete(group.characterId)) next.add(group.characterId);
                      setFolded(next);
                    }}
                  >
                    <span aria-hidden="true" className="inline-block w-3 text-mist">
                      {open ? "▾" : "▸"}
                    </span>
                    {group.name}
                    <span className="text-xs font-normal text-mist">
                      {written} of {responsesCount(group.items.length)} written
                    </span>
                  </button>
                </div>
                {open &&
                  group.items.map((item) => (
                    <div key={item.id} className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-4 pointer-coarse:size-5"
                        aria-label={`Select ${item.character_name}: ${item.question}`}
                        checked={selected.has(item.id)}
                        onChange={(e) => tick([item.id], e.target.checked)}
                      />
                      <div className="min-w-0 flex-1">
                        <ResponseEditor item={item} troupeId={cycle.troupe_id} canLog extra={<AssignSelect item={item} staff={members} />} />
                      </div>
                    </div>
                  ))}
              </section>
            );
          })}
        </>
      )}
      {selected.size > 0 && <AssignSelected cycle={cycle} ids={[...selected]} staff={members} onDone={() => setSelected(new Set())} />}
    </div>
  );
}

/** A tick for several responses at once: ticked when all are, part-ticked when some are. */
function Tick({
  label,
  ids,
  selected,
  onChange,
  hidden = false,
}: {
  label: string;
  ids: string[];
  selected: Set<string>;
  onChange: (ids: string[], on: boolean) => void;
  /** Say the label to screen readers only. */
  hidden?: boolean;
}) {
  const ticked = ids.filter((id) => selected.has(id)).length;
  const all = ids.length > 0 && ticked === ids.length;
  return (
    <label className="flex items-center gap-2 text-sm text-mist">
      <input
        type="checkbox"
        className="pointer-coarse:size-5"
        checked={all}
        ref={(box) => {
          if (box) box.indeterminate = ticked > 0 && !all;
        }}
        onChange={() => onChange(ids, !all)}
      />
      <span className={hidden ? "sr-only" : undefined}>{label}</span>
    </label>
  );
}

/** Any narrator, then each staff member with their role, as choices of who has a response. */
function AssigneeOptions({ staff, unassigned = "Unassigned" }: { staff: StaffMember[]; unassigned?: string }) {
  return (
    <>
      <option value="none">{unassigned}</option>
      <option value="any">Any narrator</option>
      {staff.map((s) => (
        <option key={s.user_id} value={s.user_id}>
          {s.display_name} ({roleLabel(s.role)})
        </option>
      ))}
    </>
  );
}

const assignment = (value: string) => (value === "any" ? { any_narrator: true } : { any_narrator: false, user_id: value === "none" ? null : value });

function assigneeName(value: string, staff: StaffMember[]): string {
  if (value === "any") return "any narrator";
  if (value === "none") return "no one";
  return staff.find((s) => s.user_id === value)?.display_name ?? "them";
}

/** The ticked responses, assigned to one person in one go, from a bar at the foot of the screen. */
function AssignSelected({ cycle, ids, staff, onDone }: { cycle: CycleOut; ids: string[]; staff: StaffMember[]; onDone: () => void }) {
  const [to, setTo] = useState("");
  const toast = useToast();
  const assign = useAction((value: string) =>
    unwrap(
      api.PUT("/api/cycles/{cycle_id}/responses/assignment", {
        params: { path: { cycle_id: cycle.id } },
        body: { response_ids: ids, ...assignment(value) },
      }),
    ),
  );
  return (
    <div data-toast-clear className="sticky bottom-0 z-10 -mx-4 flex flex-col gap-2 border-t border-ash bg-night px-4 py-3 sm:mx-0 sm:rounded-md sm:border">
      <form
        aria-label="Assign selected"
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          assign.mutate(to, {
            onSuccess: (done) => {
              toast({ message: `${done.assigned === 1 ? "1 response" : `${done.assigned} responses`} now with ${assigneeName(to, staff)}.` });
              setTo("");
              onDone();
            },
          });
        }}
      >
        <span className="text-sm text-parchment">{ids.length} selected</span>
        <Select aria-label="Assign selected to" className="w-auto" required value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="" disabled>
            Assign to…
          </option>
          <AssigneeOptions staff={staff} unassigned="No one (unassign)" />
        </Select>
        <Button type="submit" disabled={!to || assign.isPending}>
          Assign {ids.length}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Clear
        </Button>
      </form>
      <ErrorText error={assign.error} />
    </div>
  );
}

function AssignSelect({ item, staff }: { item: WorkItemOut; staff: StaffMember[] }) {
  const assign = useAction((value: string) =>
    unwrap(
      api.PUT("/api/responses/{response_id}/assignment", {
        params: { path: { response_id: item.id } },
        body: assignment(value),
      }),
    ),
  );
  return (
    <>
      <Select aria-label="Assign to" className="w-auto" value={assigneeOf(item)} onChange={(e) => assign.mutate(e.target.value)}>
        <AssigneeOptions staff={staff} />
      </Select>
      {assign.error && <ErrorText error={assign.error} />}
    </>
  );
}
