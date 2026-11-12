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
 */
export function HavenPanel({ character }: { character: CharacterOut }) {
  const data = useHaven(character.id);
  const [editing, setEditing] = useState(false);
  const found = data.data;
  if (!found) return null;
  const haven = found.haven;
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

function HavenForm({ character, found, onDone }: { character: CharacterOut; found: HavenOut; onDone: () => void }) {
  const haven = found.haven;
  const [d, setD] = useState<OwnHavenIn>({
    name: haven?.name ?? `${character.name}'s Haven`,
    description: haven?.description ?? "",
    address: haven?.address ?? "",
    map_link: haven?.map_link ?? "",
    haven_advantages: haven?.haven_advantages ?? [],
  });
  const set = (change: Partial<OwnHavenIn>) => setD((was) => ({ ...was, ...change }));
  const chosen = d.haven_advantages ?? [];
  const path = { params: { path: { character_id: character.id } }, body: d };
  const save = useAction(() => unwrap(haven ? api.PUT("/api/characters/{character_id}/haven", path) : api.POST("/api/characters/{character_id}/haven", path)), [["haven", character.id]]);
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
      <p className="text-xs text-mist">Your storytellers see your Haven on the troupe&apos;s list of locations, with each change you make.</p>
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {haven ? "Save" : "Put it on the list"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
