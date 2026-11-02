import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Button, Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

type Setting = "players" | "staff";

const OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "players",
    label: "Players keep their own",
    meaning:
      "A player adds and removes fleeting and negative status on their own character, naming who gave it. Only the one who gave a negative status, or staff, take it off early.",
  },
  {
    value: "staff",
    label: "Staff only",
    meaning: "Only storytellers and assistant storytellers add or remove status. Players still spend it at games.",
  },
];

const TITLE_OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "players",
    label: "Players choose their own",
    meaning:
      "A player chooses their character's titles from the troupe's titles of its sect, and the storytellers and assistant storytellers are told. A title only one character holds at a time is staff's to give while someone holds it.",
  },
  {
    value: "staff",
    label: "Staff only",
    meaning: "Only storytellers and assistant storytellers give and take titles, by appointment. Players still choose which of their titles is active.",
  },
];

/** Status on sheets: who adds and removes fleeting and negative status on the troupe's characters. */
export function StatusSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  return (
    <WhoSetting
      troupe={troupe}
      canEdit={canEdit}
      field="status_by"
      title="Status on sheets"
      label="Change who keeps status on sheets"
      options={OPTIONS}
      about="Who adds and removes sect status on the sheets of characters whose home is here. Storytellers and assistant storytellers always can, with a reason for the character's log."
    />
  );
}

/** Titles on sheets: whether players choose their characters' titles, or only staff give them. */
export function TitlesSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  return (
    <WhoSetting
      troupe={troupe}
      canEdit={canEdit}
      field="titles_by"
      title="Titles on sheets"
      label="Change who chooses titles"
      options={TITLE_OPTIONS}
      about="Who gives titles to characters whose home is here. Storytellers and assistant storytellers always can, from the Characters tab or the character's Status & Titles tab."
    />
  );
}

/**
 * House rule (issue #441): each character's one source of abiding status is chosen as
 * it checks in to a game, before it enters play, and fixed for the game. Off: chosen on
 * the Play View as the game begins, as the book has it.
 */
export function StatusAtCheckinSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((on: boolean) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { status_at_checkin: on } })),
  );
  const on = troupe.status_at_checkin;
  return (
    <Card title="The night's status">
      <p className="mb-3 text-sm text-mist">
        A character with more than one source of abiding status, such as a title and its social age, carries only one into a game (MET: VTM p. 311).
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "Chosen at check-in, and fixed for the game." : "Chosen on the Play View as the game begins."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Choose the night's status at check-in
              <span className="block text-xs text-mist">
                Players choose the source as they check in, and can't change it on the Play View. Storytellers and assistant storytellers can, with a reason for the game's
                log. Status given for a single night is held beside it.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}

/** A setting of who does something on the troupe's sheets: its players, or staff only. */
function WhoSetting({
  troupe,
  canEdit,
  field,
  title,
  label,
  options,
  about,
}: {
  troupe: TroupeOut;
  canEdit: boolean;
  field: "status_by" | "titles_by";
  title: string;
  label: string;
  options: { value: Setting; label: string; meaning: string }[];
  about: string;
}) {
  const [editing, setEditing] = useState<Setting | null>(null);
  const save = useAction(async (value: Setting) => {
    await unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { [field]: value } }));
    setEditing(null);
  });
  const now = troupe[field] as Setting;
  const current = options.find((o) => o.value === now) ?? options[0]!;
  return (
    <Card
      title={title}
      actions={
        canEdit &&
        editing === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label={label} onClick={() => setEditing(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">{about}</p>
      {editing === null ? (
        <p className="text-sm">
          {current.label}. <span className="text-mist">{current.meaning}</span>
        </p>
      ) : (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(editing);
          }}
        >
          {options.map((o) => (
            <label key={o.value} className="flex items-start gap-2 text-sm">
              <input type="radio" name={field} className="mt-1" checked={editing === o.value} onChange={() => setEditing(o.value)} />
              <span>
                {o.label}
                <span className="block text-xs text-mist">{o.meaning}</span>
              </span>
            </label>
          ))}
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      )}
    </Card>
  );
}
