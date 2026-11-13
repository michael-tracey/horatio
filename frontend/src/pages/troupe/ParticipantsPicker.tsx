import type { CharacterChoice, VaulderieParticipantIn } from "../../api/types";
import { partyIn } from "../../bonds";
import { Button } from "../../components/ui";
import { WhoPicker } from "./WhoPicker";

/** One row of the picker: who (as WhoPicker keeps it) and whether they gave no blood. */
export type ParticipantRow = { who: string; name: string; falseSabbat: boolean };

export const emptyRow = (): ParticipantRow => ({ who: "", name: "", falseSabbat: false });

/** The rows picked so far, as the API takes them; rows left empty are skipped. */
export function participantsIn(rows: ParticipantRow[]): VaulderieParticipantIn[] {
  return rows.flatMap((r) => {
    const party = partyIn(r.who, r.name);
    return party ? [{ ...party, false_sabbat: r.falseSabbat }] : [];
  });
}

/**
 * Who took part in a Vaulderie (#666): a character of the troupe's, or a name only, on
 * each row, each with a box for a false Sabbat, who drank but gave no blood (the
 * Errata's p. 434).
 */
export function ParticipantsPicker({
  characters,
  rows,
  onChange,
  label = "Participants",
}: {
  characters: CharacterChoice[];
  rows: ParticipantRow[];
  onChange: (rows: ParticipantRow[]) => void;
  label?: string;
}) {
  const set = (i: number, row: Partial<ParticipantRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...row } : r)));
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-xs text-mist">{label}</legend>
      <ul className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <li key={i} className="flex flex-wrap items-center gap-2">
            <div className="min-w-0 flex-1 basis-48">
              <WhoPicker
                aria-label={`Participant ${i + 1}`}
                characters={characters}
                who={r.who}
                name={r.name}
                onChange={(who, name) => set(i, { who, name })}
              />
            </div>
            <label className="flex items-center gap-1 text-xs text-mist">
              <input
                type="checkbox"
                aria-label={`Participant ${i + 1} is a false Sabbat`}
                checked={r.falseSabbat}
                onChange={(e) => set(i, { falseSabbat: e.target.checked })}
              />
              False Sabbat
            </label>
            {rows.length > 1 && (
              <button
                type="button"
                className="text-xs text-mist underline hover:text-parchment"
                aria-label={`Take out participant ${i + 1}`}
                onClick={() => onChange(rows.filter((_, j) => j !== i))}
              >
                Take out
              </button>
            )}
          </li>
        ))}
      </ul>
      <div>
        <Button type="button" variant="ghost" onClick={() => onChange([...rows, emptyRow()])}>
          Add a participant
        </Button>
      </div>
    </fieldset>
  );
}
