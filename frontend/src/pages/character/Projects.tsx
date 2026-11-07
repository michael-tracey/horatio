import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { ProjectIn, ProjectOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { projectLine, PROJECT_KINDS, projectStatus } from "./projectText";

/**
 * A character's projects (#507), work that spans several downtimes such as a Path
 * change: for its player on the Downtime tab, and for its home troupe's staff on
 * the character page. Its player proposes one, which staff confirm; staff start,
 * stop and finish them.
 */
export function ProjectsCard({ characterId }: { characterId: string }) {
  const found = useQuery({
    queryKey: ["projects", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/projects", { params: { path: { character_id: characterId } } })),
  });
  const [starting, setStarting] = useState(false);
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const { projects, paths, staff } = found.data;
  return (
    <Card title="Projects">
      <p className="mb-3 text-sm text-mist">
        Work that takes more than one downtime, such as changing Path. An action counts toward one when {staff ? "its player chooses" : "you choose"} it under
        “Counts toward”, once the cycle is complete.{" "}
        <Link to={staff ? manualLink("running-a-troupe", "projects") : manualLink("players", "projects")} className="underline hover:text-parchment">
          About projects
        </Link>
      </p>
      {projects.length === 0 ? (
        <Empty>No projects yet.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {projects.map((p) => (
            <ProjectItem key={p.id} project={p} staff={staff} characterId={characterId} />
          ))}
        </ul>
      )}
      <div className="mt-3">
        {starting ? (
          <StartProject characterId={characterId} paths={paths} staff={staff} onDone={() => setStarting(false)} />
        ) : (
          <Button variant="secondary" onClick={() => setStarting(true)}>
            {staff ? "Start a project" : "Propose a project"}
          </Button>
        )}
      </div>
    </Card>
  );
}

/** One project: its progress, its monthly rule, and what staff or its player can do with it. */
export function ProjectItem({ project: p, staff, characterId, showName = false }: { project: ProjectOut; staff: boolean; characterId: string; showName?: boolean }) {
  const act = useAction((what: "confirm" | "drop" | "sheet-changed") => {
    const params = { params: { path: { project_id: p.id } } };
    if (what === "confirm") return unwrap(api.POST("/api/projects/{project_id}/confirm", params));
    if (what === "drop") return unwrap(api.POST("/api/projects/{project_id}/drop", params));
    return unwrap(api.POST("/api/projects/{project_id}/sheet-changed", params));
  });
  const open = p.status === "proposed" || p.status === "active";
  return (
    <li aria-label={showName ? `${p.character_name}: ${p.name}` : p.name} className="flex flex-col gap-1 rounded-md border border-ash p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium text-parchment">
          {showName && <span className="text-gold">{p.character_name} · </span>}
          {p.name}
        </span>
        <Badge tone={p.status === "active" ? "gold" : p.status === "finished" ? "mist" : "blood"}>{projectStatus(p.status)}</Badge>
      </div>
      <p className="text-mist">{projectLine(p)}</p>
      {p.this_cycle != null && (
        <p className={p.starts_over ? "text-blood-bright" : "text-mist"}>
          {p.this_cycle} {p.this_cycle === 1 ? "action" : "actions"} toward it this cycle so far
          {p.starts_over && ": it starts over when the cycle completes"}.
        </p>
      )}
      {p.sheet_change_due && (
        <p role="note" className="text-gold">
          {staff ? (
            <>
              Change {p.character_name}'s Morality to {p.path} on the{" "}
              <Link to={`/characters/${characterId}`} className="underline hover:text-parchment">
                sheet
              </Link>
              : it goes down by 1 (MET: VTM p. 306).
            </>
          ) : (
            `Your storytellers will change your Morality to ${p.path}.`
          )}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {staff && p.status === "proposed" && (
          <Button onClick={() => act.mutate("confirm")} disabled={act.isPending}>
            Confirm
          </Button>
        )}
        {open && (staff || p.status === "proposed") && (
          <Button variant="ghost" onClick={() => act.mutate("drop")} disabled={act.isPending}>
            {p.status === "proposed" ? (staff ? "Decline" : "Withdraw") : "Stop"}
          </Button>
        )}
        {staff && p.sheet_change_due && (
          <Button variant="secondary" onClick={() => act.mutate("sheet-changed")} disabled={act.isPending}>
            It's on the sheet
          </Button>
        )}
      </div>
      <ErrorText error={act.error} />
    </li>
  );
}

function StartProject({ characterId, paths, staff, onDone }: { characterId: string; paths: string[]; staff: boolean; onDone: () => void }) {
  const [draft, setDraft] = useState<ProjectIn>({ kind: "path_change", name: "", path: "", with_teacher: false, target: null, monthly_minimum: null });
  const start = useAction(() => unwrap(api.POST("/api/characters/{character_id}/projects", { params: { path: { character_id: characterId } }, body: draft })));
  const set = (next: Partial<ProjectIn>) => setDraft({ ...draft, ...next });
  const path = draft.kind === "path_change";
  return (
    <form
      aria-label={staff ? "Start a project" : "Propose a project"}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        start.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="Kind">
        <Select value={draft.kind} onChange={(e) => set({ kind: e.target.value as ProjectIn["kind"] })}>
          {Object.entries(PROJECT_KINDS).map(([key, name]) => (
            <option key={key} value={key}>
              {name}
            </option>
          ))}
        </Select>
      </Field>
      {path ? (
        <>
          <Field label="New Path" hint="9 actions with a teacher who follows it, or 18 without, at least 1 every month or it starts over (MET: VTM p. 306).">
            <Select required value={draft.path ?? ""} onChange={(e) => set({ path: e.target.value })}>
              <option value="">Choose…</option>
              {paths.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!draft.with_teacher} onChange={(e) => set({ with_teacher: e.target.checked })} />
            With a teacher
          </label>
        </>
      ) : (
        <>
          <Field label="Name">
            <Input required value={draft.name ?? ""} onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Actions it takes">
              <Input type="number" min={1} max={100} required value={draft.target ?? ""} onChange={(e) => set({ target: e.target.value ? Number(e.target.value) : null })} />
            </Field>
            <Field label="At least this many a month" hint="Fewer starts it over. Leave empty for no such rule.">
              <Input
                type="number"
                min={1}
                max={100}
                value={draft.monthly_minimum ?? ""}
                onChange={(e) => set({ monthly_minimum: e.target.value ? Number(e.target.value) : null })}
              />
            </Field>
          </div>
        </>
      )}
      {!staff && <p className="text-xs text-mist">Your storytellers confirm it before actions count toward it.</p>}
      <ErrorText error={start.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={start.isPending}>
          {staff ? "Start it" : "Propose it"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
