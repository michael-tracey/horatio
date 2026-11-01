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
