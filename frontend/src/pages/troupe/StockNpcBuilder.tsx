import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, ErrorText, Field, Input, Loading, PageTitle, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { CharacterPicture } from "../character/Picture";
import { type NpcKind, groupedKinds, kindPages, resourceText } from "./npcKinds";
import { allowedPowers, expandPower, INFERNAL_INVESTMENT } from "./stockNpcs";

type StockNpc = components["schemas"]["StockNpcOut"];
type Specialization = components["schemas"]["Specialization"];

/**
 * A Stock NPC's builder (MET: VTM pp. 489–490): name, kind, rating, specializations,
 * notes and picture, with the book's stat block as the server works it out. Every
 * change is saved as it is made, so the stat block is always the saved NPC's.
 */
export function StockNpcBuilder({ troupeId }: { troupeId: string }) {
  const { characterId = "" } = useParams();
  const queryClient = useQueryClient();
  const path = { params: { path: { character_id: characterId } } };
  const character = useQuery({ queryKey: ["character", characterId], queryFn: () => unwrap(api.GET("/api/characters/{character_id}", path)) });
  const stock = useQuery({ queryKey: ["stock-npc", characterId], queryFn: () => unwrap(api.GET("/api/characters/{character_id}/npc/stock", path)) });
  const kinds = useQuery({ queryKey: ["npc-kinds"], queryFn: () => unwrap(api.GET("/api/npc-kinds")), staleTime: Infinity });
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", troupeId],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: { troupe_id: troupeId } } })),
    staleTime: 5 * 60_000,
  });
  const back = <Link to={`/troupes/${troupeId}/npcs`} className="text-sm text-mist hover:text-gold">← NPCs</Link>;
  if (character.isPending || stock.isPending || kinds.isPending || catalogue.isPending) return <Loading />;
  const error = character.error ?? stock.error ?? kinds.error ?? catalogue.error;
  if (error || !character.data || !stock.data || !kinds.data || !catalogue.data) {
    return (
      <div className="flex flex-col gap-3">
        {back}
        <ErrorText error={error} />
      </div>
    );
  }
  const names = (category: string) => catalogue.data.traits.filter((t) => t.category === category).map((t) => t.name);
  const refresh = async () => {
    await Promise.all(["stock-npc", "character", "npcs"].map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
  };
  return (
    <div className="flex flex-col gap-4">
      {back}
      <Builder key={stock.data.character_id} stock={stock.data} character={character.data} kinds={kinds.data} skills={names("skills")} disciplines={names("disciplines")} path={path} refresh={refresh} />
    </div>
  );
}

function Builder({
  stock,
  character,
  kinds,
  skills,
  disciplines,
  path,
  refresh,
}: {
  stock: StockNpc;
  character: components["schemas"]["CharacterOut"];
  kinds: NpcKind[];
  skills: string[];
  disciplines: string[];
  path: { params: { path: { character_id: string } } };
  refresh: () => Promise<void>;
}) {
  const kind = stock.kind;
  const [name, setName] = useState(character.name);
  const [notes, setNotes] = useState(stock.notes);
  const [pick, setPick] = useState("");
  useEffect(() => setNotes(stock.notes), [stock.notes]);

  // Each change goes to the server with the rest as it is saved.
  const save = useAction(async (changes: Partial<{ npc_kind: string; rating: number; specializations: Specialization[]; notes: string }>) => {
    await unwrap(
      api.PUT("/api/characters/{character_id}/npc/stock", {
        ...path,
        body: {
          npc_kind: stock.npc_kind,
          custom_kind: stock.custom_kind,
          rating: stock.rating,
          specializations: stock.specializations,
          notes: stock.notes,
          ...changes,
        },
      }),
    );
    await refresh();
  });
  const rename = useAction(async () => {
    await unwrap(api.PATCH("/api/characters/{character_id}", { ...path, body: { name } }));
    await refresh();
  });
  const allowed = allowedPowers(kind, disciplines);
  const others = disciplines.filter((d) => !allowed.includes(d));
  const add = () => {
    if (!pick) return;
    const [type, ...rest] = pick.split(":");
    save.mutate({ specializations: [...stock.specializations, { type: type as Specialization["type"], name: rest.join(":") }] });
    setPick("");
  };
  const choosable = kinds.filter((k) => !k.custom || stock.npc_kind === k.key);

  return (
    <>
      <PageTitle subtitle={`Stock NPC · ${kind.name} · ${kindPages(kind)}`}>{character.name}</PageTitle>
      <div className="grid gap-6 md:grid-cols-[3fr_2fr]">
        <div className="flex flex-col gap-6">
          <Card title="Stock NPC">
            <div className="flex flex-col gap-3">
              <div className="flex items-start gap-4">
                <CharacterPicture character={character} />
                <form
                  className="flex flex-1 items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    rename.mutate(undefined);
                  }}
                >
                  <div className="flex-1">
                    <Field label="Name">
                      <Input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
                    </Field>
                  </div>
                  <Button type="submit" variant="secondary" disabled={rename.isPending || !name.trim() || name.trim() === character.name}>
                    Rename
                  </Button>
                </form>
              </div>
              <ErrorText error={rename.error} />
              <div className="grid grid-cols-2 gap-3">
                <Field label="Kind">
                  <Select value={stock.npc_kind} disabled={save.isPending} onChange={(e) => save.mutate({ npc_kind: e.target.value })}>
                    {groupedKinds(choosable).map((g) => (
                      <optgroup key={g.label} label={g.label}>
                        {g.kinds.map((k) => (
                          <option key={k.key} value={k.key}>
                            {k.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </Select>
                </Field>
                <Field label="Rating" hint={`1 to ${kind.rating_max}`}>
                  <Select value={stock.rating} disabled={save.isPending} onChange={(e) => save.mutate({ rating: Number(e.target.value) })}>
                    {Array.from({ length: kind.rating_max }, (_, i) => i + 1).map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <ErrorText error={save.error} />
            </div>
          </Card>
          <Card title={`Specialisations (${stock.specializations.length} of ${stock.rating})`}>
            <div className="flex flex-col gap-3">
              {stock.specializations.length ? (
                <ul className="divide-y divide-ash">
                  {stock.specializations.map((s) => (
                    <li key={`${s.type}:${s.name}`} aria-label={s.name} className="flex items-center gap-3 py-1.5">
                      <span className="flex-1">{s.name}</span>
                      <Badge>{s.type === "skill" ? "Skill" : "Power"}</Badge>
                      <Button
                        type="button"
                        variant="ghost"
                        aria-label={`Remove ${s.name}`}
                        disabled={save.isPending}
                        onClick={() => save.mutate({ specializations: stock.specializations.filter((x) => x !== s) })}
                      >
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-mist">None yet. It can have as many as its rating.</p>
              )}
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  add();
                }}
              >
                <div className="flex-1">
                  <Field
                    label="Add a specialisation"
                    hint={kind.specialization_label ? `${kind.specialization_label}: a skill, or one of the kind's list.` : "A skill, or a power from the kind's list."}
                  >
                    <Select value={pick} onChange={(e) => setPick(e.target.value)}>
                      <option value="">Choose…</option>
                      <optgroup label="Skills">
                        {skills.map((n) => (
                          <option key={n} value={`skill:${n}`}>
                            {n}
                          </option>
                        ))}
                      </optgroup>
                      {allowed.length > 0 && (
                        <optgroup label={`${kind.name} list`}>
                          {allowed.map((n) => (
                            <option key={n} value={`power:${n}`}>
                              {n}
                            </option>
                          ))}
                        </optgroup>
                      )}
                      <optgroup label="Infernal (V20 LARP SRD)">
                        <option value={`power:${INFERNAL_INVESTMENT}`}>{INFERNAL_INVESTMENT}: every Dark Thaumaturgy ritual</option>
                      </optgroup>
                      <optgroup label="Other disciplines (not on the list)">
                        {others.map((n) => (
                          <option key={n} value={`power:${n}`}>
                            {n}
                          </option>
                        ))}
                      </optgroup>
                    </Select>
                  </Field>
                </div>
                <Button type="submit" disabled={!pick || save.isPending}>
                  Add
                </Button>
              </form>
            </div>
          </Card>
          <Card title="Notes">
            <Textarea aria-label="Notes" rows={4} maxLength={10000} value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== stock.notes && save.mutate({ notes })} />
          </Card>
        </div>
        <div className="flex flex-col gap-6">
          <StatBlock stock={stock} />
          <RulesCard kind={kind} />
          <MakeSheeted stock={stock} character={character} path={path} refresh={refresh} />
        </div>
      </div>
    </>
  );
}

/**
 * "Make this a full sheet…", with its confirmation. The rule it follows is written
 * out here, and in the PR, because it cannot be undone.
 */
function MakeSheeted({
  stock,
  character,
  path,
  refresh,
}: {
  stock: StockNpc;
  character: components["schemas"]["CharacterOut"];
  path: { params: { path: { character_id: string } } };
  refresh: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const convert = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/npc/sheeted", path));
    await refresh();
    navigate(`/characters/${character.id}`);
  });
  const s = stock.stats;
  const attribute = Math.min(s.pool, 10);
  const fate = stock.kind.panels.morality ? "" : ` It has no Humanity, Beast traits or Generation, as a ${stock.kind.name.toLowerCase()} has none.`;
  return (
    <Card title="Full sheet">
      <p className="mb-3 text-sm text-mist">Give this NPC a full Vampire-rules sheet, to play like any other NPC. It cannot be turned back.</p>
      <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
        Make this a full sheet…
      </Button>
      <Dialog title={`Make ${character.name} a full sheet?`} open={open} onClose={() => setOpen(false)}>
        <div className="flex flex-col gap-3 p-4 text-sm">
          <p>
            {character.name} keeps its name, kind, picture and notes (the notes go in the log). Its sheet starts from the Stock data like this:
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              Physical, Social and Mental are each its test pool, rating × 2: {attribute}
              {s.pool > 10 && " (the most an attribute can be)"}.
            </li>
            <li>Each skill specialization becomes that skill at its rating, {Math.min(s.rating, 5)} (5 at most).</li>
            <li>Each discipline specialization becomes that discipline at its rating (5 at most).</li>
            <li>Powers the Vampire rules have no trait for stay on the {stock.kind.name} rules card.</li>
          </ul>
          <p className="text-mist">It becomes a sheeted NPC with the {stock.kind.name} rules card, and uses {stock.kind.resource.name} in place of Blood.{fate}</p>
          <ErrorText error={convert.error} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={convert.isPending} onClick={() => convert.mutate(undefined)}>
              Make a full sheet
            </Button>
          </div>
        </div>
      </Dialog>
    </Card>
  );
}

/** The block the book prints (pp. 490–505), as the server works it out. */
export function StatBlock({ stock }: { stock: StockNpc }) {
  const s = stock.stats;
  return (
    <Card title="Stat block">
      <ul className="flex flex-col gap-1.5 text-sm" aria-label="Stat block">
        <li>
          Test pool {s.pool} in most challenges
        </li>
        {s.skill_pools.map((p) => (
          <li key={p.name}>
            {p.name} {p.pool}
          </li>
        ))}
        {s.powers.map((p) => (
          <li key={p.name}>{expandPower(p.name, p.dots)}</li>
        ))}
        {s.built_in.map((p) => (
          <li key={p.name}>
            {p.name}
            {p.dots !== null && ` ${p.dots === "rating" ? s.rating : p.dots}`}
            {p.note && <span className="text-mist"> ({p.note})</span>}
          </li>
        ))}
        <li>{resourceText(s.resource)}</li>
        <li>{s.health} health</li>
        <li className="text-mist">No Willpower: no retests unless it overbids</li>
      </ul>
    </Card>
  );
}

/** The kind's rules, short, with where the book has them. */
export function RulesCard({ kind }: { kind: NpcKind }) {
  return (
    <Card title={`${kind.name} rules card`}>
      <p className="mb-2 text-xs text-mist">{kindPages(kind)} · Stock NPCs, pp. 489–490</p>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {kind.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
        {kind.numina.map((n) => (
          <li key={n.name}>
            {n.name} (p. {n.page}): {n.levels.join("; ")}
          </li>
        ))}
        {kind.powers.map((p) => (
          <li key={p.name}>
            {p.name}
            {p.note && `: ${p.note}`}
          </li>
        ))}
      </ul>
    </Card>
  );
}
