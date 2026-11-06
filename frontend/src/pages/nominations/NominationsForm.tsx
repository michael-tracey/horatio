import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { AboutOut, MyNominationOut, MyNominationsOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Field, Loading, Select, Textarea } from "../../components/ui";

/** An about choice as a select's value: "c:<id>" for a character, "u:<id>" for staff, "" for no one. */
const aboutValue = (a: Pick<AboutOut, "character_id" | "user_id"> | null | undefined) =>
  a?.character_id ? `c:${a.character_id}` : a?.user_id ? `u:${a.user_id}` : "";

function aboutBody(value: string) {
  const [kind, id] = value.split(":");
  return { about_character_id: kind === "c" ? id : null, about_user_id: kind === "u" ? id : null };
}

type Draft = { text: string; about: string };

/**
 * The downtime form's Player Nominations (#470), when the troupe uses them: short
 * notes praising other people's roleplaying, as many as the player likes, each with
 * an optional link to a character in the troupe or one of its staff. They save as
 * they are added, apart from the form's answers, and spend no actions. Each can be
 * changed while the downtime can, until it is published.
 */
export function NominationsForm({ characterId }: { characterId: string }) {
  const path = { params: { path: { character_id: characterId } } };
  const key = ["my-nominations", characterId];
  const client = useQueryClient();
  const mine = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/downtime/nominations", path)),
  });
  // Each change answers with the whole list; nothing else on the page changes with it.
  const saved = (found: MyNominationsOut) => client.setQueryData(key, found);
  const add = useMutation({
    mutationFn: (d: Draft) => unwrap(api.POST("/api/characters/{character_id}/downtime/nominations", { ...path, body: { text: d.text, ...aboutBody(d.about) } })),
    onSuccess: saved,
  });
  const [draft, setDraft] = useState<Draft>({ text: "", about: "" });

  if (mine.isPending) return <Loading />;
  if (mine.error) return <ErrorText error={mine.error} />;
  const m = mine.data;
  return (
    <Card title="Player Nominations">
      <p className="text-sm text-mist">
        A line or two praising someone’s roleplaying: a player, a character, a storyteller, or everyone. They’re shared with the troupe without your name, and the
        storytellers read them first. They don’t use any actions.
      </p>
      {!m.submitted && m.nominations.length > 0 && <p className="mt-2 text-sm text-mist">The storytellers read them once you submit your downtime.</p>}
      {m.nominations.length > 0 && (
        <ul aria-label="Your nominations" className="mt-3 divide-y divide-ash border-y border-ash">
          {m.nominations.map((n) => (
            <Written key={n.id} characterId={characterId} nomination={n} choices={m.choices} most={m.most} onSaved={saved} />
          ))}
        </ul>
      )}
      <form
        className="mt-4 flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(draft, { onSuccess: () => setDraft({ text: "", about: "" }) });
        }}
      >
        <Field label="New nomination" hint={`${draft.text.length} of ${m.most} characters`}>
          <Textarea rows={3} maxLength={m.most} value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
        </Field>
        <AboutField choices={m.choices} value={draft.about} onChange={(about) => setDraft({ ...draft, about })} />
        <ErrorText error={add.error} />
        <div>
          <Button type="submit" variant="secondary" disabled={add.isPending || !draft.text.trim()}>
            Add nomination
          </Button>
        </div>
      </form>
    </Card>
  );
}

function AboutField({ choices, value, onChange, label = "About (optional)" }: { choices: AboutOut[]; value: string; onChange: (value: string) => void; label?: string }) {
  const characters = choices.filter((a) => a.character_id);
  const staff = choices.filter((a) => a.user_id);
  return (
    <Field label={label} hint="Its player sees the nominations about their character.">
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">No one in particular</option>
        <optgroup label="Characters">
          {characters.map((a) => (
            <option key={aboutValue(a)} value={aboutValue(a)}>
              {a.name}
            </option>
          ))}
        </optgroup>
        <optgroup label="Staff">
          {staff.map((a) => (
            <option key={aboutValue(a)} value={aboutValue(a)}>
              {a.name}
            </option>
          ))}
        </optgroup>
      </Select>
    </Field>
  );
}

/** One the player wrote: its text and who it's about, to change or take out until it is published. */
function Written({
  characterId,
  nomination: n,
  choices,
  most,
  onSaved,
}: {
  characterId: string;
  nomination: MyNominationOut;
  choices: AboutOut[];
  most: number;
  onSaved: (found: MyNominationsOut) => void;
}) {
  const path = { params: { path: { character_id: characterId, nomination_id: n.id } } };
  const [editing, setEditing] = useState<Draft | null>(null);
  const change = useMutation({
    mutationFn: (d: Draft) => unwrap(api.PUT("/api/characters/{character_id}/downtime/nominations/{nomination_id}", { ...path, body: { text: d.text, ...aboutBody(d.about) } })),
    onSuccess: (found) => {
      onSaved(found);
      setEditing(null);
    },
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/characters/{character_id}/downtime/nominations/{nomination_id}", path)),
    onSuccess: onSaved,
  });
  if (editing)
    return (
      <li className="py-3">
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate(editing);
          }}
        >
          <Field label="Nomination" hint={`${editing.text.length} of ${most} characters`}>
            <Textarea rows={3} maxLength={most} value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} />
          </Field>
          <AboutField choices={choices} value={editing.about} onChange={(about) => setEditing({ ...editing, about })} />
          <ErrorText error={change.error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={change.isPending || !editing.text.trim()}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      </li>
    );
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm whitespace-pre-line wrap-anywhere">{n.text}</p>
        {(n.about || n.published) && (
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-mist">
            {n.about && <span>About {n.about.name}</span>}
            {n.published && <Badge>Published</Badge>}
          </p>
        )}
        <ErrorText error={remove.error} />
      </div>
      {!n.published && (
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" aria-label={`Change the nomination “${n.text.slice(0, 40)}”`} onClick={() => setEditing({ text: n.text, about: aboutValue(n.about) })}>
            Change
          </Button>
          <Button variant="ghost" aria-label={`Take out the nomination “${n.text.slice(0, 40)}”`} disabled={remove.isPending} onClick={() => remove.mutate()}>
            Take out
          </Button>
        </div>
      )}
    </li>
  );
}
