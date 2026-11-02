import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { willpowerText } from "../troupe/teacherRules";

/**
 * Teaching asked of this character at the cost of its Willpower (horatio.teaching):
 * its player confirms, which spends the Willpower here, or says no. Shows nothing
 * when nothing is asked.
 */
export function TeachingAsks({ characterId }: { characterId: string }) {
  const asked = useQuery({
    queryKey: ["teaching", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/teaching", { params: { path: { character_id: characterId } } })),
  });
  const answer = useAction((body: { id: string; teach: boolean }) =>
    unwrap(
      body.teach
        ? api.POST("/api/teachings/{teaching_id}/confirm", { params: { path: { teaching_id: body.id } } })
        : api.POST("/api/teachings/{teaching_id}/refuse", { params: { path: { teaching_id: body.id } } }),
    ),
  );
  if (!asked.data?.asked.length) return null;
  return (
    <section aria-label="Teaching asked of you" className="mb-3 flex flex-col gap-2 rounded-md border border-gold/50 bg-gold/5 p-3 text-sm">
      {asked.data.asked.map((a) => (
        <div key={a.id} className="flex flex-col gap-2">
          <p>
            <span className="text-gold">{a.what}?</span> It costs {willpowerText(a.willpower, a.games)}: rest does not bring it back until then.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button disabled={answer.isPending} onClick={() => answer.mutate({ id: a.id, teach: true })}>
              Teach, spending {a.willpower} Willpower
            </Button>
            <Button variant="ghost" disabled={answer.isPending} onClick={() => answer.mutate({ id: a.id, teach: false })}>
              Say no
            </Button>
          </div>
        </div>
      ))}
      <ErrorText error={answer.error} />
    </section>
  );
}
