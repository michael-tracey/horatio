import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { ErrorText, Field, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { ownEntryLabel } from "../../influenceLookups";

type Fields = Record<string, unknown> | undefined;

/**
 * What a discovery block hides: one of the character's own logged actions, picked
 * from a list, or someone else's, described in the answer. Players never see
 * anyone else's actions. Staff confirm which entry it is.
 */
export function BlockTarget({ characterId, fields, onChange }: { characterId: string; fields: Fields; onChange: (fields: Record<string, unknown>) => void }) {
  const dates = useDates();
  const whose = fields?.block === "own" || fields?.block === "other" ? fields.block : "";
  const entry = typeof fields?.block_entry === "string" ? fields.block_entry : "";
  const choices = useQuery({
    queryKey: ["block-choices", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/downtime/block-choices", { params: { path: { character_id: characterId } } })),
    enabled: whose === "own",
  });
  const since = choices.data && dates.date(choices.data.window.since);
  const hint = !choices.data
    ? null
    : choices.data.entries.length
      ? `Your actions in the log since ${since}.`
      : `None of your actions since ${since} are in the log. Describe it in your answer instead.`;

  return (
    <div className="grid gap-2 sm:col-span-2 sm:grid-cols-2">
      <Field label="Whose action to hide">
        <Select value={whose} onChange={(e) => onChange({ ...fields, block: e.target.value || undefined, block_entry: undefined })}>
          <option value="">Choose…</option>
          <option value="own">One of mine</option>
          <option value="other">Someone else's</option>
        </Select>
      </Field>
      {whose === "own" && (
        <Field label="Your action" hint={hint}>
          <Select className="w-full min-w-0" value={entry} onChange={(e) => onChange({ ...fields, block_entry: e.target.value || undefined })}>
            <option value="">Choose…</option>
            {choices.data?.entries.map((e) => (
              <option key={e.id} value={e.id}>
                {ownEntryLabel(e, dates)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {whose === "other" && (
        <p className="self-end text-xs text-mist">Describe it in your answer: what was done, where and when. Staff find it in the troupe's log.</p>
      )}
      <ErrorText error={choices.error} />
    </div>
  );
}
