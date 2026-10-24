import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SharedChoicesOut } from "../../api/types";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { RECORD_ONLY, SharedBackgroundView } from "./SharedBackground";
import { sharersText, totalText } from "./sharedBackgrounds";

/**
 * The troupe's shared backgrounds, for its storytellers and assistants: set one
 * up, and open one to keep its log.
 */
export function SharedBackgroundsTab({ troupeId }: { troupeId: string }) {
  return (
    <Routes>
      <Route index element={<List troupeId={troupeId} />} />
      <Route path=":sharedId" element={<One troupeId={troupeId} />} />
    </Routes>
  );
}

function List({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const [adding, setAdding] = useState(false);
  const shared = useQuery({
    queryKey: ["troupe-shared", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/shared-backgrounds", path)),
  });
  const choices = useQuery({
    queryKey: ["shared-choices", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/shared-backgrounds/choices", path)),
  });
  if (shared.isPending || choices.isPending) return <Loading />;
  if (shared.error || choices.error) return <ErrorText error={shared.error ?? choices.error} />;

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Shared backgrounds"
        actions={
          !adding && (
            <Button variant="secondary" onClick={() => setAdding(true)}>
              Set up a shared background
            </Button>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">
          A {choices.data.backgrounds.join(", ")} that a coterie, pack or gang pools together, each putting in dots of their own; the group's is never more than{" "}
          {choices.data.most} ({choices.data.page}). The players of the characters sharing one see it and log their uses. {RECORD_ONLY}
        </p>
        {adding && <SetUpForm troupeId={troupeId} choices={choices.data} onDone={() => setAdding(false)} />}
      </Card>
      {shared.data.length === 0 ? (
        <Empty>No shared backgrounds yet.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {shared.data.map((s) => (
            <li key={s.id} className="rounded-md border border-ash bg-dusk p-3 text-sm">
              <Link to={s.id} className="text-gold hover:text-parchment">
                {s.name}
              </Link>{" "}
              <span className="text-mist">
                · {s.background} · {totalText(s)} · {s.entries.filter((e) => e.kind === "use").length} uses
              </span>
              <p className="mt-1">{sharersText(s.sharers)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function One({ troupeId }: { troupeId: string }) {
  const { sharedId = "" } = useParams();
  const navigate = useNavigate();
  const shared = useQuery({
    queryKey: ["shared", sharedId],
    queryFn: () => unwrap(api.GET("/api/shared-backgrounds/{shared_id}", { params: { path: { shared_id: sharedId } } })),
  });
  const back = `/troupes/${troupeId}/shared`;
  return (
    <div className="flex flex-col gap-4">
      <Link to={back} className="text-sm text-mist hover:text-gold">
        ← All shared backgrounds
      </Link>
      {shared.isPending ? <Loading /> : shared.error ? <ErrorText error={shared.error} /> : <SharedBackgroundView shared={shared.data} onDeleted={() => navigate(back)} />}
    </div>
  );
}

type Row = { character_id: string; dots: number };

function SetUpForm({ troupeId, choices, onDone }: { troupeId: string; choices: SharedChoicesOut; onDone: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [background, setBackground] = useState(choices.backgrounds[0] ?? "");
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState<Row[]>([{ character_id: "", dots: 1 }]);
  const setRow = (i: number, change: Partial<Row>) => setRows(rows.map((r, n) => (n === i ? { ...r, ...change } : r)));
  const chosen = rows.filter((r) => r.character_id);
  const save = useAction(async () => {
    const made = await unwrap(
      api.POST("/api/troupes/{troupe_id}/shared-backgrounds", {
        params: { path: { troupe_id: troupeId } },
        body: { name, background, notes, contributions: chosen },
      }),
    );
    onDone();
    navigate(`/troupes/${troupeId}/shared/${made.id}`);
  });
  return (
    <form
      aria-label="Set up a shared background"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="The coterie's Haven" />
        </Field>
        <Field label="Background">
          <Select value={background} onChange={(e) => setBackground(e.target.value)}>
            {choices.backgrounds.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="What it gives (optional)" hint="Such as the haven's advantages, which the sharers choose together.">
        <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm text-mist">Sharing it, and the dots each puts in</legend>
        {rows.map((row, i) => (
          <div key={i} className="flex flex-wrap items-end gap-2">
            <div className="min-w-48 flex-1">
              <Field label={`Character ${i + 1}`}>
                <Select value={row.character_id} onChange={(e) => setRow(i, { character_id: e.target.value })}>
                  <option value="">Choose…</option>
                  {choices.characters
                    .filter((c) => c.id === row.character_id || !rows.some((r) => r.character_id === c.id))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                        {c.kind === "npc" ? " (NPC)" : ""}
                      </option>
                    ))}
                </Select>
              </Field>
            </div>
            <div className="w-24">
              <Field label={`Dots ${i + 1}`}>
                <Input type="number" min={1} max={10} value={row.dots} onChange={(e) => setRow(i, { dots: Number(e.target.value) })} />
              </Field>
            </div>
            {rows.length > 1 && (
              <Button type="button" variant="ghost" aria-label={`Remove character ${i + 1}`} onClick={() => setRows(rows.filter((_, n) => n !== i))}>
                ×
              </Button>
            )}
          </div>
        ))}
        <Button type="button" variant="secondary" className="self-start" onClick={() => setRows([...rows, { character_id: "", dots: 1 }])}>
          Add a character
        </Button>
      </fieldset>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !name.trim() || !background || chosen.length === 0 || chosen.some((r) => r.dots < 1)}>
          Set up
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
