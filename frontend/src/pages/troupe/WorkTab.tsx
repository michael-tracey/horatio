import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { ResponseEditor } from "../../components/ResponseEditor";
import { Badge, Button, Card, Empty, ErrorText, Loading } from "../../components/ui";
import { useAction, useMe } from "../../hooks";

export function WorkTab({ troupeId }: { troupeId: string }) {
  const cycles = useQuery({
    queryKey: ["work-cycles", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/work-cycles", { params: { path: { troupe_id: troupeId } } })),
  });
  if (cycles.isPending) return <Loading />;
  if (cycles.error) return <ErrorText error={cycles.error} />;
  if (!cycles.data.length) return <Empty>No downtimes to answer yet.</Empty>;
  return (
    <Card title="Downtimes to answer">
      <ul className="divide-y divide-ash">
        {cycles.data.map((c) => (
          <li key={c.id}>
            <Link to={c.id} className="flex items-center justify-between py-3 hover:text-gold">
              <span>{c.name}</span>
              <Badge tone={c.status === "open" ? "gold" : "mist"}>{c.status}</Badge>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** A staff member's own work in one cycle: what is assigned to them, and for
 * narrators the any-narrator pool. No character sheets here, by design. */
export function MyWork({ troupeId, canLog = false }: { troupeId: string; canLog?: boolean }) {
  const { cycleId = "" } = useParams();
  const me = useMe();
  const items = useQuery({
    queryKey: ["mine", cycleId],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/responses/mine", { params: { path: { cycle_id: cycleId } } })),
  });
  const accept = useAction((id: string) => unwrap(api.POST("/api/responses/{response_id}/accept", { params: { path: { response_id: id } } })));
  const decline = useAction((id: string) => unwrap(api.POST("/api/responses/{response_id}/decline", { params: { path: { response_id: id } } })));

  if (items.isPending) return <Loading />;
  if (items.error) return <ErrorText error={items.error} />;
  const assigned = items.data.filter((i) => i.assigned_to_user_id === me.data?.id);
  const pool = items.data.filter((i) => i.assigned_to_any_narrator);

  return (
    <div className="flex flex-col gap-6">
      <Card title={`Assigned to you (${assigned.filter((i) => i.status === "written").length}/${assigned.length} written)`}>
        {assigned.length === 0 ? (
          <Empty>Nothing assigned to you.</Empty>
        ) : (
          <div className="flex flex-col gap-3">
            {assigned.map((item) => (
              <ResponseEditor
                key={item.id}
                item={item}
                troupeId={troupeId}
                canLog={canLog}
                extra={
                  item.status !== "written" && (
                    <Button variant="ghost" onClick={() => decline.mutate(item.id)}>
                      Decline
                    </Button>
                  )
                }
              />
            ))}
          </div>
        )}
      </Card>
      {pool.length > 0 && (
        <Card title="Open to any narrator">
          <ul className="flex flex-col gap-3">
            {pool.map((item) => (
              <li key={item.id} className="flex flex-col gap-2 rounded-md border border-ash p-3 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm">
                  <strong className="text-gold">{item.character_name}</strong> · {item.question}
                  <span className="mt-1 block text-mist">{item.answer}</span>
                </span>
                <Button variant="secondary" onClick={() => accept.mutate(item.id)}>
                  Take it
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <ErrorText error={accept.error ?? decline.error} />
    </div>
  );
}
