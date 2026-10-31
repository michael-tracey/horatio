import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { Change, QuestRequestOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { CHANGE_KINDS, emptyChange, modifiersText, NEGATIVES, questName, type ChangeKind } from "../quests/locationQuests";
import { guidanceText } from "../quests/quests";

type Category = "simple" | "complex" | "epic";

function bookGuidance(category: string, difficulty: number): { requirements: number; scenarios: number } {
  const per: Record<string, [number, number]> = { simple: [1, 0], complex: [2, 1], epic: [3, 2] };
  const [r, s] = per[category] ?? [1, 0];
  return { requirements: r * difficulty, scenarios: Math.max(1, s * difficulty) };
}

/**
 * Building a quest that changes a location when it is completed (Vol. II Issue 1,
 * pp. 118-129): from a player's request, or from the location's page. The server
 * works out the category and difficulty, with their reasons, and the requirements
 * the location's qualities suggest; staff pick from them and can change the rest.
 */
export function LocationQuestBuilder({ troupeId, locationId, request, start }: { troupeId: string; locationId: string; request?: QuestRequestOut; start?: Change | null }) {
  const navigate = useNavigate();
  const [change, setChange] = useState<Change>(start ?? emptyChange());
  const [leaderId, setLeaderId] = useState("");
  const [name, setName] = useState<string | null>(null);
  const [objective, setObjective] = useState(request?.objective ?? "");
  const [category, setCategory] = useState<Category | null>(null);
  const [difficulty, setDifficulty] = useState<number | null>(null);
  const [dropped, setDropped] = useState<number[]>([]);
  const location = useQuery({
    queryKey: ["location", locationId],
    queryFn: () => unwrap(api.GET("/api/locations/{location_id}", { params: { path: { location_id: locationId } } })),
  });
  const catalogue = useQuery({
    queryKey: ["location-catalogue", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/locations/catalogue", { params: { path: { troupe_id: troupeId } } })),
  });
  const characters = useQuery({
    queryKey: ["quest-characters", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-characters", { params: { path: { troupe_id: troupeId } } })),
    enabled: !request,
  });
  const plan = useQuery({
    queryKey: ["location-quest-plan", locationId, change, leaderId, request?.id],
    queryFn: () =>
      unwrap(
        api.POST("/api/locations/{location_id}/quest-plan", {
          params: { path: { location_id: locationId } },
          body: { change, leader_id: leaderId || null, request_id: request?.id ?? null },
        }),
      ),
  });
  const build = useAction(async () => {
    const p = plan.data!;
    const made = await unwrap(
      api.POST("/api/troupes/{troupe_id}/location-quests", {
        params: { path: { troupe_id: troupeId } },
        body: {
          location_id: locationId,
          change,
          request_id: request?.id ?? null,
          leader_id: request ? null : leaderId || null,
          name: name ?? questName(change, location.data?.name ?? ""),
          objective,
          category: category ?? p.category,
          difficulty: difficulty ?? p.difficulty,
          downtime_only: false,
          staff_notes: "",
          requirements: p.suggestions.filter((_, i) => !dropped.includes(i)).map((s) => ({ options: s.options })),
        },
      }),
    );
    navigate(`/troupes/${troupeId}/quests/${made.id}`);
  });
  if (location.isPending || catalogue.isPending) return <Loading />;
  if (location.error || catalogue.error) return <ErrorText error={location.error ?? catalogue.error} />;
  const l = location.data;
  const set = (c: Partial<Change>) => {
    setChange({ ...change, ...c });
    setCategory(null);
    setDifficulty(null);
    setDropped([]);
  };
  const p = plan.data;
  const shownCategory = category ?? p?.category ?? "simple";
  const shownDifficulty = difficulty ?? p?.difficulty ?? l.rating;
  const qualities = catalogue.data.qualities.filter((q) => q.kind !== "elysium" && (q.kind !== "iconic" || l.kind === "iconic"));

  return (
    <Card title={request ? `A location quest for ${request.character_name}` : `A quest for ${l.name}`}>
      {request && <p className="mb-3 text-sm text-mist">From the request: “{request.objective}”{request.reason ? ` Why: ${request.reason}` : ""}</p>}
      <form
        aria-label="Build a location quest"
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          build.mutate(undefined);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="What the quest does">
            <Select value={change.kind} disabled={!!request} onChange={(e) => set({ ...emptyChange(e.target.value as ChangeKind) })}>
              {CHANGE_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Field>
          {!request && (
            <Field label="Leader">
              <Select value={leaderId} onChange={(e) => setLeaderId(e.target.value)}>
                <option value="">No one yet</option>
                {characters.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {change.kind === "swap" && (
            <Field label="The quality it loses">
              <Select value={change.swap_out} onChange={(e) => set({ swap_out: e.target.value })}>
                <option value="">Choose</option>
                {[...new Set(l.qualities.map((q) => q.name))].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {(change.kind === "quality" || change.kind === "swap") && (
            <>
              <Field label="The quality it gains">
                <Select value={change.quality} onChange={(e) => set({ quality: e.target.value })}>
                  <option value="">Choose</option>
                  {qualities.map((q, i) => (
                    <option key={`${q.name}${i}`} value={q.name}>
                      {q.name}
                    </option>
                  ))}
                </Select>
              </Field>
              {qualities.find((q) => q.name === change.quality)?.detail && (
                <Field label={qualities.find((q) => q.name === change.quality)!.detail}>
                  <Input value={change.detail} onChange={(e) => set({ detail: e.target.value })} />
                </Field>
              )}
            </>
          )}
          {change.kind === "negative" && (
            <>
              <Field label="Negative quality">
                <Select value={change.negative} onChange={(e) => set({ negative: e.target.value })}>
                  <option value="">Choose</option>
                  {NEGATIVES.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Field>
              <label className="flex min-h-10 items-center gap-2 text-sm">
                <input type="checkbox" checked={!!change.secret} onChange={(e) => set({ secret: e.target.checked })} />
                Secret from the controller
              </label>
            </>
          )}
          {change.kind === "infiltrate" && (
            <Field label="Its victory condition" hint="One goal: steal, plant or rescue.">
              <Input value={change.victory} onChange={(e) => set({ victory: e.target.value })} />
            </Field>
          )}
        </div>
        {plan.error ? (
          <ErrorText error={plan.error} />
        ) : !p ? (
          <Loading />
        ) : (
          <>
            {p.refusal && (
              <div role="alert">
                <Notice>{p.refusal}</Notice>
              </div>
            )}
            <p className="text-sm">
              On success, {p.change}.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Category" hint={p.category_note || undefined}>
                <Select value={shownCategory} onChange={(e) => setCategory(e.target.value as Category)}>
                  <option value="simple">Simple</option>
                  <option value="complex">Complex</option>
                  <option value="epic">Epic</option>
                </Select>
              </Field>
              <Field label="Difficulty" hint={`From ${l.name}: ${modifiersText(p.modifiers)}.`}>
                <Select value={shownDifficulty} onChange={(e) => setDifficulty(Number(e.target.value))}>
                  {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <p className="text-sm text-mist">{guidanceText(bookGuidance(shownCategory, shownDifficulty))}</p>
            <fieldset aria-label="Suggested requirements" className="flex flex-col gap-1 text-sm">
              <legend className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">Suggested requirements</legend>
              {p.suggestions.length === 0 ? (
                <p className="text-mist">Its qualities suggest none; add requirements on the quest.</p>
              ) : (
                p.suggestions.map((s, i) => (
                  <label key={i} className="flex min-h-8 items-center gap-2">
                    <input
                      type="checkbox"
                      checked={!dropped.includes(i)}
                      onChange={(e) => setDropped(e.target.checked ? dropped.filter((d) => d !== i) : [...dropped, i])}
                    />
                    <span>
                      {s.label} <span className="text-mist">({s.source})</span>
                    </span>
                  </label>
                ))
              )}
              {p.fewer.map((f) => (
                <p key={f} className="text-gold">
                  {f}
                </p>
              ))}
              <p className="text-xs text-mist">Change them, or add others, on the quest once it is built.</p>
            </fieldset>
          </>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Quest name">
            <Input required value={name ?? questName(change, l.name)} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Objective">
              <Textarea rows={2} value={objective} onChange={(e) => setObjective(e.target.value)} />
            </Field>
          </div>
        </div>
        <div>
          <Button type="submit" disabled={build.isPending || !p || !!p.refusal}>
            Build the quest
          </Button>
        </div>
        <ErrorText error={build.error} />
      </form>
    </Card>
  );
}
