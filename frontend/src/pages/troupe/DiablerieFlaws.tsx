import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

type Setting = "leave" | "remove" | "keep_xp";

const OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "leave",
    label: "Leave the flaw",
    meaning: "It stays on the sheet, and staff see a warning on the diablerie form.",
  },
  {
    value: "remove",
    label: "Remove the flaw and the XP it gave",
    meaning: "It comes off, and a correction line in the XP history takes back what it gave (as far as the character has the XP).",
  },
  {
    value: "keep_xp",
    label: "Remove the flaw and keep the XP",
    meaning: "It comes off, and the XP it gave stays with the character.",
  },
];

/** House rule: what recording a diablerie does to a Lesser Generation or Thin Blooded flaw its holder has. */
export function DiablerieFlaws({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [editing, setEditing] = useState<Setting | null>(null);
  const save = useAction(async (setting: Setting) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/diablerie-flaws", { ...path, body: { setting } }));
    setEditing(null);
  });
  if (!troupe.data) return null;
  const now = troupe.data.diablerie_flaws as Setting;
  const current = OPTIONS.find((o) => o.value === now) ?? OPTIONS[0]!;
  return (
    <Card
      title="Diablerie and Lesser Generation"
      actions={
        canEdit &&
        editing === null && (
          <Button variant="ghost" className="min-h-8 px-2" aria-label="Change what diablerie does to Lesser Generation" onClick={() => setEditing(now)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        What recording a diablerie does to a character who holds Lesser Generation or Thin Blooded. The diablerie form shows staff what this will do before they confirm.
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
              <input type="radio" name="diablerie-flaws" className="mt-1" checked={editing === o.value} onChange={() => setEditing(o.value)} />
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
