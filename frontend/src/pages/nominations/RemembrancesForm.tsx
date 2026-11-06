import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { MyMemoryOut, MyRemembrancesOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Badge, Button, Card, ErrorText, Field, Loading, Textarea } from "../../components/ui";

/**
 * The downtime form's Remembrances (#471): each character the cycle asks memories
 * of, with their portrait and why they left, and a box for one memory of each. It
 * saves apart from the form's answers, spends no actions, and can be changed while
 * the downtime can, until it is published.
 */
export function RemembrancesForm({ characterId }: { characterId: string }) {
  const key = ["my-remembrances", characterId];
  const mine = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/downtime/remembrances", { params: { path: { character_id: characterId } } })),
  });
  if (mine.isPending) return <Loading />;
  if (mine.error) return <ErrorText error={mine.error} />;
  const m = mine.data;
  if (!m.remembered.length) return null;
  return (
    <Card title="Remembrances">
      <p className="text-sm text-mist">
        The troupe remembers those who have left play. Share a memory of each, if you have one: they’re shared with the troupe without your name, and the storytellers
        read them first. They don’t use any actions.
      </p>
      {!m.submitted && m.remembered.some((r) => r.text) && <p className="mt-2 text-sm text-mist">The storytellers read them once you submit your downtime.</p>}
      <ul className="mt-3 flex flex-col gap-4">
        {m.remembered.map((r) => (
          <Memory key={r.remembrance_id} characterId={characterId} remembered={r} most={m.most} queryKey={key} />
        ))}
      </ul>
    </Card>
  );
}

function Memory({ characterId, remembered: r, most, queryKey }: { characterId: string; remembered: MyMemoryOut; most: number; queryKey: string[] }) {
  const client = useQueryClient();
  const path = { params: { path: { character_id: characterId, remembrance_id: r.remembrance_id } } };
  const [text, setText] = useState(r.text ?? "");
  const saved = (found: MyRemembrancesOut) => client.setQueryData(queryKey, found);
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/api/characters/{character_id}/downtime/remembrances/{remembrance_id}", { ...path, body: { text } })),
    onSuccess: saved,
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/characters/{character_id}/downtime/remembrances/{remembrance_id}", path)),
    onSuccess: (found) => {
      saved(found);
      setText("");
    },
  });
  const changed = text.trim() !== (r.text ?? "");
  return (
    <li aria-label={`A memory of ${r.name}`} className="flex gap-3">
      <Avatar name={r.name} picture={r.picture} clan={r.clan} size="md" />
      <div className="min-w-0 flex-1">
        <p className="font-display text-base text-parchment">{r.name}</p>
        {r.reason && <p className="text-xs text-mist">{r.reason}</p>}
        {r.published ? (
          <>
            <p className="mt-2 text-sm whitespace-pre-line wrap-anywhere">{r.text}</p>
            <Badge className="mt-1">Published</Badge>
          </>
        ) : (
          <form
            className="mt-2 flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <Field label={`Your memory of ${r.name}`} hint={`${text.length} of ${most} characters`}>
              <Textarea rows={3} maxLength={most} value={text} onChange={(e) => setText(e.target.value)} />
            </Field>
            <ErrorText error={save.error ?? remove.error} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" variant="secondary" disabled={save.isPending || !text.trim() || !changed}>
                {r.text ? "Save changes" : "Save memory"}
              </Button>
              {r.text && (
                <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
                  Take out
                </Button>
              )}
              {r.text && !changed && <span className="text-xs text-mist">Saved</span>}
            </div>
          </form>
        )}
      </div>
    </li>
  );
}
