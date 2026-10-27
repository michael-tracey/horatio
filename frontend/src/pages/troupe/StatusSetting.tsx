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

/** Status on sheets: who adds and removes fleeting and negative status on the troupe's characters. */
export function StatusSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const [editing, setEditing] = useState<Setting | null>(null);
  const save = useAction(async (status_by: Setting) => {
    await unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { status_by } }));
    setEditing(null);
  });
  const now = troupe.status_by as Setting;
  const current = OPTIONS.find((o) => o.value === now) ?? OPTIONS[0]!;
  return (
    <Card
      title="Status on sheets"
      actions={
        canEdit &&
        editing === null && (
          <Button variant="ghost" className="min-h-8 px-2" aria-label="Change who keeps status on sheets" onClick={() => setEditing(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        Who adds and removes sect status on the sheets of characters whose home is here. Storytellers and assistant storytellers always can, with a reason for the
        character's log.
      </p>
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
          {OPTIONS.map((o) => (
            <label key={o.value} className="flex items-start gap-2 text-sm">
              <input type="radio" name="status-by" className="mt-1" checked={editing === o.value} onChange={() => setEditing(o.value)} />
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
