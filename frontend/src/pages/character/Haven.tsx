import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, HavenOut, OwnHavenIn } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Field, Input, Textarea } from "../../components/ui";
import { WebLink } from "../../components/WebLink";
import { useAction } from "../../hooks";
import { canChoose, countText } from "./haven";

export function useHaven(characterId: string) {
  return useQuery({
    queryKey: ["haven", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/haven", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
}

/**
 * The player's own Haven, under the Haven row of their sheet (#682): its name,
 * where it is, what it is like and its advantages, which they keep. Staff keep
 * the rest of it on the troupe's list of locations, and see every change.
 * Before any troupe has accepted the character it is a draft (#683), which the
 * first troupe to accept it puts on its list.
 */
export function HavenPanel({ character }: { character: CharacterOut }) {
  const data = useHaven(character.id);
  const [editing, setEditing] = useState(false);
  const found = data.data;
  if (!found) return null;
  const haven = found.haven;
  const draft = found.draft;
  const link = "mt-0.5 text-mist underline hover:text-gold";
  return (
    <section className="mb-1 ml-3 border-l border-ash pl-3 text-xs" aria-label="Your Haven">
      {haven ? (
        <>
          <p>
            <span className="text-parchment">{haven.name}</span>
            {haven.address && <span className="text-mist"> · {haven.address}</span>}
            {haven.map_link && (
              <>
                <span className="text-mist"> · </span>
                <WebLink url={haven.map_link} className="text-gold hover:text-parchment">
                  Map
                </WebLink>
              </>
            )}
          </p>
          {haven.description && <p className="whitespace-pre-wrap text-mist">{haven.description}</p>}
          <p className="text-mist">
            {haven.haven_advantages.length > 0
              ? `Advantages: ${haven.haven_advantages.map((a) => (haven.haven_free.includes(a) ? `${a} (free)` : a)).join(", ")}`
              : "No advantages chosen yet."}
          </p>
          {haven.negatives.map((n) => (
            <p key={n.name} className="text-blood-bright">
              {n.name} ×{n.level}: {n.effect}
            </p>
          ))}
          {haven.haven_over && <p className="text-gold">{haven.haven_over}</p>}
          {haven.read_only ? (
            <p className="text-mist">{haven.read_only}</p>
          ) : (
            <button type="button" className={link} onClick={() => setEditing(true)}>
              Edit your Haven
            </button>
          )}
        </>
      ) : draft ? (
        <>
          <p>
            <span className="text-parchment">{draft.name}</span>
            {draft.address && <span className="text-mist"> · {draft.address}</span>}
          </p>
          {draft.description && <p className="whitespace-pre-wrap text-mist">{draft.description}</p>}
          <p className="text-mist">
            {draft.haven_advantages.length > 0
              ? `Advantages: ${draft.haven_advantages.map((a) => (draft.haven_free.includes(a) ? `${a} (free)` : a)).join(", ")}`
              : "No advantages chosen yet."}
          </p>
          {draft.haven_over && <p className="text-gold">{draft.haven_over}</p>}
          <p className="text-mist">{draftNote(character.name, found)}</p>
          {(found.drafting || !found.cannot_create) && (
            <button type="button" className={link} onClick={() => setEditing(true)}>
              {found.drafting ? "Edit your Haven" : "Put your Haven on the list"}
            </button>
          )}
        </>
      ) : found.cannot_create ? (
        <p className="text-mist">{found.cannot_create}</p>
      ) : (
        <button type="button" className={link} onClick={() => setEditing(true)}>
          Name your Haven and choose its advantages
        </button>
      )}
      <Dialog title="Your Haven" open={editing} onClose={() => setEditing(false)} wide phoneFull>
        <HavenForm character={character} found={found} onDone={() => setEditing(false)} />
      </Dialog>
    </section>
  );
}

/** What happens to a draft Haven: kept until a troupe accepts the character, or waiting for its player. */
function draftNote(name: string, found: HavenOut): string {
  if (found.drafting) return `Kept with ${name} until a troupe accepts them: that troupe's storytellers then see it on their list of locations.`;
  return found.cannot_create ?? "It couldn't go on the troupe's list when they accepted you: put it there yourself, with another name if that one is taken.";
}

function HavenForm({ character, found, onDone }: { character: CharacterOut; found: HavenOut; onDone: () => void }) {
  const haven = found.haven;
  const start = haven ?? found.draft;
  const [d, setD] = useState<OwnHavenIn>({
    name: start?.name ?? `${character.name}'s Haven`,
    description: start?.description ?? "",
    address: start?.address ?? "",
    map_link: start?.map_link ?? "",
    haven_advantages: start?.haven_advantages ?? [],
  });
  const set = (change: Partial<OwnHavenIn>) => setD((was) => ({ ...was, ...change }));
  const chosen = d.haven_advantages ?? [];
  const path = { params: { path: { character_id: character.id } }, body: d };
  const save = useAction(
    () =>
      unwrap(
        haven
          ? api.PUT("/api/characters/{character_id}/haven", path)
          : found.drafting
            ? api.PUT("/api/characters/{character_id}/haven/draft", path)
            : api.POST("/api/characters/{character_id}/haven", path),
      ),
    [["haven", character.id]],
  );
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        await save.mutateAsync(undefined);
        onDone();
      }}
    >
      <Field label="Name">
        <Input value={d.name} required maxLength={120} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Description" hint="What it is like, for you and your storytellers.">
        <Textarea value={d.description} maxLength={5000} onChange={(e) => set({ description: e.target.value })} />
      </Field>
      <Field label="Address">
        <Input value={d.address} maxLength={500} onChange={(e) => set({ address: e.target.value })} />
      </Field>
      <Field label="Map link">
        <Input type="url" value={d.map_link} placeholder="https://" onChange={(e) => set({ map_link: e.target.value })} />
      </Field>
      <fieldset className="text-sm">
        <legend className="mb-1 text-mist">Advantages: one for each dot of Haven · {countText(chosen, found.advantages, found.dots)}</legend>
        <div className="flex flex-col gap-1">
          {found.advantages.map((a) => (
            <label key={a.name} className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-1"
                checked={chosen.includes(a.name)}
                disabled={!canChoose(a.name, chosen, found.advantages, found.dots)}
                onChange={(e) => set({ haven_advantages: e.target.checked ? [...chosen, a.name] : chosen.filter((x) => x !== a.name) })}
              />
              <span>
                <span className="text-parchment">{a.name}</span>
                {a.free && <span className="text-gold"> · Free with {a.free_with}</span>}
                {!a.allowed && <span className="text-mist"> · Needs {a.needs}</span>}
                <span className="block text-xs text-mist">{a.text}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-mist">MET: VTM p. 102</p>
      </fieldset>
      <p className="text-xs text-mist">
        {found.drafting
          ? `Kept with ${character.name} until a troupe accepts them: that troupe's storytellers then see it on their list of locations.`
          : "Your storytellers see your Haven on the troupe's list of locations, with each change you make."}
      </p>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {haven || found.drafting ? "Save" : "Put it on the list"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/**
 * Naming the Haven in creation (#683), under the Backgrounds step's picks once the
 * character has a dot of it: optional, and the same form as the sheet's. Saving the
 * step asks for the Haven again, so a dot or a skill gone shows as too many here.
 */
export function WizardHaven({ character }: { character: CharacterOut }) {
  return (
    <section className="mt-6 text-sm" aria-labelledby="wizard-haven">
      <h3 id="wizard-haven" className="text-xs tracking-wide text-mist uppercase">
        Your Haven
      </h3>
      <p className="mt-1 mb-2 text-xs text-mist">
        Optional: name it and choose its advantages now, or later from the sheet. The troupe that accepts {character.name} puts it on its list of locations.
      </p>
      <HavenPanel character={character} />
    </section>
  );
}
