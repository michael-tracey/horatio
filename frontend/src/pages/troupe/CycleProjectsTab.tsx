import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { CycleOut } from "../../api/types";
import { Empty, ErrorText, Loading } from "../../components/ui";
import { ProjectItem } from "../character/Projects";

/**
 * The troupe's projects (#507), by character: what the cycle has spent on each so
 * far, and which start over when it completes, so staff can see it coming.
 */
export function CycleProjectsTab({ cycle }: { cycle: CycleOut }) {
  const found = useQuery({
    queryKey: ["cycle-projects", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/projects", { params: { path: { cycle_id: cycle.id } } })),
  });
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  if (found.data.length === 0) return <Empty>No projects yet. Start one from a character's Projects tab, or confirm one a player proposes.</Empty>;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-mist">When the cycle is marked complete, each project goes up by the actions spent on it in submitted downtimes.</p>
      <ul className="flex flex-col gap-3">
        {found.data.map((p) => (
          <ProjectItem key={p.id} project={p} staff characterId={p.character_id} showName questsOn={cycle.quests_enabled} />
        ))}
      </ul>
    </div>
  );
}
