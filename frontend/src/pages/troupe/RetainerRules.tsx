import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { bodyOf, draftOf, draftProblem, MOST_GROWTH, MOST_UPKEEP, type RulesDraft } from "./retainerRules";

/**
 * House rules for Retainers (issue #442), neither in the book and each off unless
 * switched on: upkeep, in Blood or Willpower, a game or a month; and growth, XP a
 * month given as a downtime cycle closes.
 */
export function RetainerRules({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const rules = useQuery({ queryKey: ["retainer-rules", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/retainer-rules", path)) });
  const [draft, setDraft] = useState<RulesDraft | null>(null);
  const save = useAction(async (value: RulesDraft) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/retainer-rules", { ...path, body: bodyOf(value) }));
    setDraft(null);
  });
  if (rules.isPending) return <Loading />;
  if (rules.error) return <ErrorText error={rules.error} />;
  const now = rules.data;
  const problem = draft && draftProblem(draft);
  const upkeep = (patch: Partial<RulesDraft["upkeep"]>) => draft && setDraft({ ...draft, upkeep: { ...draft.upkeep, ...patch } });

  return (
    <Card
      title="Retainers"
      actions={
        canEdit &&
        draft === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change Retainer rules" onClick={() => setDraft(draftOf(now))}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        The book has neither of these. Upkeep is taken on the Play View as each character&rsquo;s night starts, at check-in or its first tap, as its own line in the
        night&rsquo;s log. A Retainer its character can&rsquo;t pay for is marked neglected and staff are told; what follows is up to you, and nothing is lost by
        itself. Growth goes to the NPC linked to a Retainer, for staff to spend, or is banked on the Retainer while none is. A lost Retainer pays and gains nothing.
      </p>
      {draft === null ? (
        <dl className="grid gap-1 text-sm sm:grid-cols-[8rem_1fr]">
          <dt className="text-mist">Upkeep</dt>
          <dd>{now.upkeep_text ?? "None."}</dd>
          <dt className="text-mist">Growth</dt>
          <dd>{now.growth_text ?? "None."}</dd>
        </dl>
      ) : (
        <form
          className="flex flex-col gap-4 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (!problem) save.mutate(draft);
          }}
        >
          <fieldset className="flex flex-col gap-2">
            <label className="flex min-h-10 items-center gap-2">
              <input type="checkbox" checked={draft.upkeepOn} onChange={(e) => setDraft({ ...draft, upkeepOn: e.target.checked })} />
              Retainers cost upkeep
            </label>
            {draft.upkeepOn && (
              <div className="ml-6 flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                  Each
                  <Input type="number" min={1} max={MOST_UPKEEP} required value={draft.upkeep.amount} onChange={(e) => upkeep({ amount: Number(e.target.value) })} className="w-20" />
                </label>
                <label className="flex flex-col gap-1">
                  Of
                  <Select value={draft.upkeep.pool} onChange={(e) => upkeep({ pool: e.target.value as "blood" | "willpower" })}>
                    <option value="blood">Blood</option>
                    <option value="willpower">Willpower</option>
                  </Select>
                </label>
                <label className="flex flex-col gap-1">
                  Taken
                  <Select value={draft.upkeep.per} onChange={(e) => upkeep({ per: e.target.value as "game" | "month" })}>
                    <option value="game">Each game, as the night starts</option>
                    <option value="month">Each month</option>
                  </Select>
                </label>
                {draft.upkeep.per === "month" && (
                  <label className="flex flex-col gap-1">
                    When
                    <Select value={draft.upkeep.month_at} onChange={(e) => upkeep({ month_at: e.target.value as "game" | "downtime" })}>
                      <option value="game">At the month&rsquo;s first game</option>
                      <option value="downtime">As a downtime cost, when a cycle closes</option>
                    </Select>
                  </label>
                )}
                <label className="flex min-h-10 items-center gap-2">
                  <input type="checkbox" checked={draft.upkeep.ghouls_only} onChange={(e) => upkeep({ ghouls_only: e.target.checked })} />
                  Ghoul Retainers only
                </label>
              </div>
            )}
          </fieldset>
          <fieldset className="flex flex-col gap-2">
            <label className="flex min-h-10 items-center gap-2">
              <input type="checkbox" checked={draft.growthOn} onChange={(e) => setDraft({ ...draft, growthOn: e.target.checked })} />
              Retainers gain XP
            </label>
            {draft.growthOn && (
              <label className="ml-6 flex flex-col gap-1">
                XP a month for each Retainer, given as a downtime cycle closes
                <Input type="number" min={1} max={MOST_GROWTH} required value={draft.growth} onChange={(e) => setDraft({ ...draft, growth: Number(e.target.value) })} className="w-20" />
              </label>
            )}
          </fieldset>
          {problem && <p className="text-blood-bright">{problem}</p>}
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending || !!problem}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      )}
    </Card>
  );
}
