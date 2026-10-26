import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SceneOut, SceneSummary } from "../../api/types";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Notice } from "../../components/ui";
import { useDates } from "../../dates";
import { useMe } from "../../hooks";
import { abilities } from "../troupe/roles";
import { SaveDeviceScene } from "./DeviceScene";

// How often to look for scenes other staff made or changed, as the Play View does.
export const SCENE_REFRESH = 15_000;

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

const path = (troupeId: string) => ({ params: { path: { troupe_id: troupeId } } });
const scenePath = (troupeId: string, sceneId: string) => ({ params: { path: { troupe_id: troupeId, scene_id: sceneId } } });

/** Making, renaming and removing a troupe's scenes, each refreshing the lists and the scene. */
export function useSceneChanges(troupeId: string) {
  const client = useQueryClient();
  const refresh = async (scene?: SceneOut) => {
    if (scene) client.setQueryData(["scene", scene.id], scene);
    await client.invalidateQueries({ queryKey: ["scenes", troupeId] });
  };
  const create = useMutation({
    mutationFn: (body: { name: string; characters?: string[] }) => unwrap(api.POST("/api/troupes/{troupe_id}/scenes", { ...path(troupeId), body })),
    onSuccess: refresh,
  });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => unwrap(api.PATCH("/api/troupes/{troupe_id}/scenes/{scene_id}", { ...scenePath(troupeId, id), body: { name } })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/troupes/{troupe_id}/scenes/{scene_id}", scenePath(troupeId, id))),
    onSuccess: async (_, id) => {
      client.removeQueries({ queryKey: ["scene", id] });
      await refresh();
    },
  });
  return { create, rename, remove };
}

/**
 * The troupe's scenes, for the staff running a game: each one's name, who made it,
 * how many are in it and when it was last used. Any of them opens one; its maker
 * or the lead storyteller renames or removes it.
 */
export function ScenesPage() {
  const { troupeId = "" } = useParams();
  const navigate = useNavigate();
  const me = useMe();
  const [mine, setMine] = useState(true);
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path(troupeId))),
  });
  const scenes = useQuery({
    queryKey: ["scenes", troupeId, mine],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/scenes", { params: { path: { troupe_id: troupeId }, query: { mine } } })),
    refetchInterval: SCENE_REFRESH,
    refetchOnWindowFocus: true,
  });
  const changes = useSceneChanges(troupeId);
  const lead = troupe.data ? abilities(troupe.data.my_role, me.data?.is_custodian ?? false).lead : false;

  return (
    <div className="min-h-screen bg-night pb-16 text-parchment">
      <header className="sticky top-0 z-10 border-b border-ash bg-night/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link to={`/troupes/${troupeId}/play`} className="inline-flex min-h-10 items-center text-sm text-mist hover:text-parchment">
            ← {troupe.data?.name ?? "Back"}
          </Link>
          <h1 className="text-lg">Scenes</h1>
        </div>
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 pt-3">
        <SaveDeviceScene troupeId={troupeId} onSave={(name, characters) => changes.create.mutateAsync({ name, characters })} />
        <NewScene onCreate={async (name) => navigate(`/play/troupes/${troupeId}/scenes/${(await changes.create.mutateAsync({ name })).id}`)} error={changes.create.error} pending={changes.create.isPending} />
        <div className="flex gap-1" role="group" aria-label="Whose scenes">
          {(
            [
              [true, "Mine"],
              [false, "All"],
            ] as const
          ).map(([value, label]) => (
            <Button key={label} variant={mine === value ? "secondary" : "ghost"} aria-pressed={mine === value} onClick={() => setMine(value)}>
              {label}
            </Button>
          ))}
        </div>
        {scenes.isPending ? (
          <Loading />
        ) : scenes.error ? (
          <ErrorText error={scenes.error} />
        ) : scenes.data.length === 0 ? (
          <Empty>{mine ? "You have no scenes in this troupe yet. Make one above, or look at All." : "No scenes in this troupe yet. Make one above."}</Empty>
        ) : (
          <ul className="divide-y divide-ash rounded-lg border border-ash bg-dusk">
            {scenes.data.map((s) => (
              <SceneRow key={s.id} troupeId={troupeId} scene={s} changes={changes} />
            ))}
          </ul>
        )}
        <ErrorText error={changes.rename.error ?? changes.remove.error} />
        {lead && <ClearOldScenes troupeId={troupeId} />}
      </main>
    </div>
  );
}

function NewScene({ onCreate, error, pending }: { onCreate: (name: string) => Promise<unknown>; error: unknown; pending: boolean }) {
  const [name, setName] = useState("");
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) void onCreate(name.trim()).catch(() => undefined);
      }}
    >
      <div className="min-w-48 flex-1">
        <Field label="Name of a new scene">
          <Input value={name} maxLength={80} placeholder="Elysium, ballroom" onChange={(e) => setName(e.target.value)} />
        </Field>
      </div>
      <Button type="submit" disabled={pending || !name.trim()}>
        New scene
      </Button>
      <div className="basis-full">
        <ErrorText error={error} />
      </div>
    </form>
  );
}

type Changes = ReturnType<typeof useSceneChanges>;

function SceneRow({ troupeId, scene, changes }: { troupeId: string; scene: SceneSummary; changes: Changes }) {
  const dates = useDates();
  const [renaming, setRenaming] = useState(false);
  const [removing, setRemoving] = useState(false);
  return (
    <li className="flex flex-col gap-2 px-3 py-2.5" aria-label={scene.name}>
      {renaming ? (
        <RenameScene
          name={scene.name}
          pending={changes.rename.isPending}
          onSave={async (name) => {
            await changes.rename.mutateAsync({ id: scene.id, name });
            setRenaming(false);
          }}
          onCancel={() => setRenaming(false)}
        />
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <span className="min-w-40 flex-1">
            <Link to={`/play/troupes/${troupeId}/scenes/${scene.id}`} className="text-parchment underline-offset-2 hover:underline">
              {scene.name}
            </Link>
            <span className="block text-xs text-mist">
              {scene.mine ? "Yours" : `By ${scene.created_by_name}`} · {scene.count === 1 ? "1 character" : `${scene.count} characters`} · last used {dates.dateTime(scene.last_used_at)}
            </span>
          </span>
          {scene.can_change && (
            <span className="flex gap-1">
              <Button variant="ghost" className="px-2" aria-label={`Rename ${scene.name}`} onClick={() => setRenaming(true)}>
                Rename
              </Button>
              <Button variant="ghost" className="px-2" aria-label={`Remove ${scene.name}`} onClick={() => setRemoving(true)}>
                Remove
              </Button>
            </span>
          )}
        </div>
      )}
      {removing && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span>Remove “{scene.name}”? Its characters and what they spent stay as they are.</span>
          <Button variant="danger" disabled={changes.remove.isPending} onClick={() => changes.remove.mutate(scene.id)}>
            Remove the scene
          </Button>
          <Button variant="ghost" onClick={() => setRemoving(false)}>
            Cancel
          </Button>
        </div>
      )}
    </li>
  );
}

/** A scene's name being changed, in place. */
export function RenameScene({ name, pending, onSave, onCancel, className }: { name: string; pending: boolean; onSave: (name: string) => Promise<unknown>; onCancel: () => void; className?: string }) {
  const [text, setText] = useState(name);
  return (
    <form
      className={cx("flex flex-wrap items-end gap-2", className)}
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) void onSave(text.trim()).catch(() => undefined);
      }}
    >
      <div className="min-w-48 flex-1">
        <Field label="Name of the scene">
          <Input value={text} maxLength={80} autoFocus onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Escape" && onCancel()} />
        </Field>
      </div>
      <Button type="submit" disabled={pending || !text.trim()}>
        Save
      </Button>
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}

/** For the lead storyteller: clear out scenes from past games. */
function ClearOldScenes({ troupeId }: { troupeId: string }) {
  const client = useQueryClient();
  const dates = useDates();
  const [day, setDay] = useState("");
  const [asking, setAsking] = useState(false);
  const clear = useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/troupes/{troupe_id}/scenes", {
          params: { path: { troupe_id: troupeId }, query: { unused_since: dates.fromInput(`${day}T00:00`).toISOString() } },
        }),
      ),
    onSuccess: async () => {
      setAsking(false);
      await client.invalidateQueries({ queryKey: ["scenes", troupeId] });
    },
  });
  return (
    <Card title="Old scenes">
      <p className="mb-3 text-sm text-mist">Remove every scene in the troupe, whoever made it, that nobody has opened or changed since a day. Their characters stay as they are.</p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-44">
          <Field label="Not used since">
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </Field>
        </div>
        {asking ? (
          <>
            <Button variant="danger" disabled={clear.isPending} onClick={() => clear.mutate()}>
              Remove them
            </Button>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <Button variant="secondary" disabled={!day} onClick={() => setAsking(true)}>
            Remove scenes not used since…
          </Button>
        )}
      </div>
      {clear.data && <div className="mt-3"><Notice>{clear.data.removed === 1 ? "1 scene was removed." : `${clear.data.removed} scenes were removed.`}</Notice></div>}
      <ErrorText error={clear.error} />
    </Card>
  );
}
