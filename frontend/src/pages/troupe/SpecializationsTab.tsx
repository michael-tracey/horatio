import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { PartPicker } from "../../components/PartPicker";
import { Badge, Button, Card, Empty, ErrorText, Loading, Textarea } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { kindGroups, kindLabel, kindSlug } from "./specializations";

/**
 * The troupe's own lists of specialisations: the areas its Influences cover, the
 * notable people Contacts can be. Where a kind has a list, characters playing by
 * this troupe's rules choose from it; otherwise they use the catalogue or name
 * their own. One kind at a time, each a part of its own (/specializations/lore),
 * chosen in a `PartPicker` grouped as on a sheet (#906).
 */
export function SpecializationsTab({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const kinds = useQuery({
    queryKey: ["troupe-specializations", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/specializations", { params: { path: { troupe_id: troupeId } } })),
  });
  if (kinds.isPending) return <Loading />;
  if (kinds.error) return <ErrorText error={kinds.error} />;
  const base = `/troupes/${troupeId}/specialisations`;
  const first = kinds.data[0];
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        Each kind of specialisation can use the rule set's list (players may also name their own), or a list of this troupe's.
        It applies to characters whose home troupe this is, or who are being built for it.
      </p>
      <PartPicker
        label="Specialisations"
        parts={kindGroups(kinds.data).map((group) => ({
          label: group.label,
          parts: group.kinds.map((k) => ({ to: `${base}/${kindSlug(k.category)}`, label: kindLabel(k.name) })),
        }))}
      >
        <Routes>
          {first && <Route index element={<Navigate to={`${base}/${kindSlug(first.category)}`} replace />} />}
          <Route path=":kind" element={<KindPage troupeId={troupeId} kinds={kinds.data} canEdit={canEdit} />} />
        </Routes>
      </PartPicker>
    </div>
  );
}

function KindPage({ troupeId, kinds, canEdit }: { troupeId: string; kinds: TroupeKind[]; canEdit: boolean }) {
  const { kind: slug = "" } = useParams();
  const kind = kinds.find((k) => kindSlug(k.category) === slug);
  if (!kind) return <Empty>There is no such kind of specialisation.</Empty>;
  return <KindCard key={kind.category} troupeId={troupeId} kind={kind} canEdit={canEdit} />;
}

type TroupeKind = { category: string; name: string; group: string; parent_name: string; catalogue: string[]; troupe: string[] | null };

function KindCard({ troupeId, kind, canEdit }: { troupeId: string; kind: TroupeKind; canEdit: boolean }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState((kind.troupe ?? []).join("\n"));
  const save = useRulesAction((names: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/specializations/{category}", {
        params: { path: { troupe_id: troupeId, category: kind.category } },
        body: { names },
      }),
    ),
  );
  const shown = kind.troupe ?? kind.catalogue;
  return (
    <Card
      title={kind.name}
      actions={kind.troupe ? <Badge tone="gold">House rule</Badge> : <Badge>The rule set's</Badge>}
    >
      <p className="mb-2 text-xs text-mist">Specialisations of {kind.parent_name}.</p>
      {editing ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(text.split("\n"));
            setEditing(false);
          }}
        >
          <Textarea
            aria-label={`${kind.name}, one per line`}
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="One per line"
          />
          <div className="flex flex-wrap gap-2">
            <Button type="submit">Save</Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="text-sm">{shown.length ? shown.join(", ") : <span className="text-mist">No options listed; players name their own.</span>}</p>
          {canEdit && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setText((kind.troupe ?? kind.catalogue).join("\n"));
                  setEditing(true);
                }}
              >
                {kind.troupe ? "Edit our list" : "Make our own list"}
              </Button>
              {kind.troupe && (
                <Button variant="ghost" onClick={() => save.mutate([])}>
                  Use the rule set's
                </Button>
              )}
            </div>
          )}
        </>
      )}
      <ErrorText error={save.error} />
    </Card>
  );
}
