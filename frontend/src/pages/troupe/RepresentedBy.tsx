import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { WhosWhoEntry } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";

// The choice for words of the player's own, such as "Anarch".
const OWN_WORDS = "own";

/**
 * Who speaks at court for a character of a clan without a seat (issue #267): one of
 * the seated clans, or a few words of the player's own. Its player sets it, and
 * staff who give titles can change it.
 */
export function RepresentedBy({ troupeId, entry, seated, canSet }: { troupeId: string; entry: WhosWhoEntry; seated: string[]; canSet: boolean }) {
  const [editing, setEditing] = useState(false);
  const current = entry.represented_by;
  const [choice, setChoice] = useState("");
  const [words, setWords] = useState("");
  const named = useClanName();
  const save = useAction((represented_by: string | null) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/represented-by", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { represented_by },
      }),
    ),
  );
  const start = () => {
    const isClan = current !== null && seated.includes(current);
    setChoice(current === null ? "" : isClan ? current : OWN_WORDS);
    setWords(current !== null && !isClan ? current : "");
    setEditing(true);
  };

  if (!editing)
    return (
      <span className="flex flex-wrap items-baseline gap-x-2 text-mist">
        Represented by: {current ? named(current) : "nobody yet"}
        {canSet && (
          <button type="button" className="text-xs underline hover:text-gold" aria-label={`Change who represents ${entry.name}`} onClick={start}>
            Change
          </button>
        )}
      </span>
    );
  return (
    <form
      className="flex flex-col gap-2 rounded-md border border-ash p-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(choice === OWN_WORDS ? words : choice || null, { onSuccess: () => setEditing(false) });
      }}
    >
      <Select aria-label={`Who represents ${entry.name}`} value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">Nobody yet</option>
        {seated.map((clan) => (
          <option key={clan} value={clan}>
            {named(clan)}
          </option>
        ))}
        <option value={OWN_WORDS}>In your own words…</option>
      </Select>
      {choice === OWN_WORDS && (
        <Input aria-label="In your own words" placeholder="Anarch, Independent…" maxLength={60} value={words} onChange={(e) => setWords(e.target.value)} />
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
      <ErrorText error={save.error} />
    </form>
  );
}
