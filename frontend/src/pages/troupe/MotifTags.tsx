import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { MotifTagOut, SettingEntryOut } from "../../api/types";
import { Badge, Button, Card, ErrorText, Loading } from "../../components/ui";
import { useSetting } from "./SettingDocument";
import { toggled, touchedText } from "./motifTags";

/**
 * A scene's or quest's themes and moods from the troupe's setting (#880), for staff
 * only: its tags as chips, and, for those who may, a way to change them. Tagging
 * changes nothing players read.
 */
export function MotifTags({ troupeId, tags, canTag, onSave }: { troupeId: string; tags: MotifTagOut[]; canTag: boolean; onSave: (ids: string[]) => Promise<unknown> }) {
  const [picked, setPicked] = useState<string[] | null>(null);
  const save = useMutation({
    mutationFn: onSave,
    onSuccess: () => setPicked(null),
  });
  return (
    <div className="flex flex-col gap-2 text-sm" role="group" aria-label="Themes and moods">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-mist">Themes and moods:</span>
        {tags.length === 0 && picked === null && <span className="text-mist">none tagged</span>}
        {picked === null &&
          tags.map((t) => (
            <Badge key={t.id} tone={t.kind === "theme" ? "gold" : "mist"}>
              {t.name}
            </Badge>
          ))}
        {canTag && picked === null && (
          <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => setPicked(tags.map((t) => t.id))}>
            {tags.length ? "Change tags" : "Tag it"}
          </button>
        )}
      </div>
      {picked !== null && (
        <TagPicker troupeId={troupeId} picked={picked} onToggle={(id) => setPicked(toggled(picked, id))} onSave={() => save.mutate(picked)} onCancel={() => setPicked(null)} pending={save.isPending} />
      )}
      <ErrorText error={save.error} />
    </div>
  );
}

function TagPicker({
  troupeId,
  picked,
  onToggle,
  onSave,
  onCancel,
  pending,
}: {
  troupeId: string;
  picked: string[];
  onToggle: (id: string) => void;
  onSave: () => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const setting = useSetting(troupeId);
  if (setting.isPending) return <Loading />;
  if (setting.error) return <ErrorText error={setting.error} />;
  const { themes, moods } = setting.data;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-ash p-3">
      {themes.length + moods.length === 0 ? (
        <p className="text-mist">
          The troupe's setting has no themes or moods yet. Write them under{" "}
          <Link to={`/troupes/${troupeId}/settings`} className="underline hover:text-parchment">
            Troupe settings
          </Link>
          .
        </p>
      ) : (
        <>
          <Choices label="Themes" entries={themes} picked={picked} onToggle={onToggle} />
          <Choices label="Moods" entries={moods} picked={picked} onToggle={onToggle} />
          <p className="text-xs text-mist">Only staff see tags.</p>
        </>
      )}
      <div className="flex gap-2">
        {themes.length + moods.length > 0 && (
          <Button type="button" className="min-h-8 px-3" disabled={pending} onClick={onSave}>
            Save tags
          </Button>
        )}
        <Button type="button" variant="ghost" className="min-h-8 px-3" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function Choices({ label, entries, picked, onToggle }: { label: string; entries: SettingEntryOut[]; picked: string[]; onToggle: (id: string) => void }) {
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs tracking-wide text-mist uppercase">{label}</span>
      <ul aria-label={label} className="flex flex-wrap gap-2">
        {entries.map((e) => {
          const on = picked.includes(e.id);
          return (
            <li key={e.id}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onToggle(e.id)}
                className={`min-h-8 rounded-full border px-3 text-sm ${on ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment hover:border-mist"}`}
              >
                {e.name}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * For running staff on the Setting tab: each theme and mood with the scenes and quests
 * tagged with it, and how often, those nothing has touched yet among them.
 */
export function MotifsTouched({ troupeId }: { troupeId: string }) {
  const touched = useQuery({
    queryKey: ["setting-tags", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/setting/tags", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
  return (
    <Card title="Themes and moods touched">
      <p className="mb-3 text-sm text-mist">
        Only staff see this. Tag the troupe's scenes and quests with the setting's themes and moods, on each scene and quest, to see which the chronicle touches and which it hasn't yet.
      </p>
      {touched.isPending ? (
        <Loading />
      ) : touched.error ? (
        <ErrorText error={touched.error} />
      ) : touched.data.length === 0 ? (
        <p className="text-sm text-mist">The setting has no themes or moods yet.</p>
      ) : (
        <ul aria-label="Themes and moods touched" className="flex flex-col gap-2 text-sm">
          {touched.data.map((m) => {
            const none = m.scenes.length + m.quests.length === 0;
            return (
              <li key={m.id} aria-label={m.name} className="flex flex-col gap-0.5">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className={m.kind === "theme" ? "text-gold" : "text-parchment"}>{m.name}</span>
                  <span className="text-xs text-mist">{m.kind === "theme" ? "Theme" : "Mood"}</span>
                  <span className={none ? "text-mist italic" : "text-parchment"}>{touchedText(m)}</span>
                </div>
                {m.scenes.length > 0 && (
                  <TaggedLine
                    label="Scenes"
                    items={m.scenes.map((s) => ({
                      id: s.id,
                      name: s.name,
                      to: `/play/troupes/${troupeId}/scenes/${s.id}`,
                    }))}
                  />
                )}
                {m.quests.length > 0 && (
                  <TaggedLine
                    label="Quests"
                    items={m.quests.map((q) => ({
                      id: q.id,
                      name: q.name,
                      to: `/troupes/${troupeId}/quests/${q.id}`,
                    }))}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function TaggedLine({ label, items }: { label: string; items: { id: string; name: string; to: string }[] }) {
  return (
    <p className="text-mist">
      {label}:{" "}
      {items.map((item, i) => (
        <span key={item.id}>
          {i > 0 && ", "}
          <Link to={item.to} className="underline hover:text-parchment">
            {item.name}
          </Link>
        </span>
      ))}
    </p>
  );
}
