import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Field, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * For staff: the character's game badge. What others can see or sense comes
 * from the sheet (the rules data says which traits show); staff add anything
 * else in a note, then print the badge.
 */
export function BadgeButton({ character }: { character: CharacterOut }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
        Badge
      </Button>
      <Dialog title={`${character.name}'s badge`} open={open} onClose={() => setOpen(false)}>
        <BadgeNote character={character} onDone={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

function BadgeNote({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const path = { params: { path: { character_id: character.id } } };
  const note = useQuery({
    queryKey: ["visible-note", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/visible-note", path)),
  });
  const badge = useQuery({
    queryKey: ["badge", character.id, null],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/badge", path)),
  });
  const [typed, setTyped] = useState<string | null>(null);
  const text = typed ?? note.data?.note ?? "";
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/characters/{character_id}/visible-note", { ...path, body: { note: text } }));
    onDone();
  });
  const noted = new Set((note.data?.note ?? "").split("\n").filter(Boolean));
  const fromSheet = (badge.data?.badges[0]?.visible ?? []).filter((v) => !noted.has(v));

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="text-sm">
        <p className="text-mist">From the sheet, shown in reversed text at the foot of the badge:</p>
        {fromSheet.length ? (
          <ul className="mt-1 rounded bg-blood px-3 py-1.5 text-parchment">
            {fromSheet.map((v) => (
              <li key={v}>{v}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-mist italic">Nothing others can see.</p>
        )}
      </div>
      <Field label="Also shown on the badge" hint="Anything else others can see or sense about the character, one per line.">
        <Textarea rows={3} maxLength={500} value={text} onChange={(e) => setTyped(e.target.value)} placeholder="Smells of grave dirt" />
      </Field>
      <ErrorText error={save.error ?? note.error} />
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" onClick={() => window.open(`/print/characters/${character.id}/badge`, "_blank", "noopener")}>
          Print badge
        </Button>
        <Button type="submit" disabled={save.isPending || typed === null}>
          Save note
        </Button>
      </div>
    </form>
  );
}
