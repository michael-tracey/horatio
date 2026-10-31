import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterQuestsOut, PlayerQuestOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, RichText, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { NEGATIVES, REQUEST_KINDS, type RequestKind } from "../quests/locationQuests";
import { outcomeText, questStatus, questType, requestStatus, resultText, roleText } from "../quests/quests";

/** The character's quests: asking for one, following requests, and the quests it can see. */
export function QuestsTab({ characterId }: { characterId: string }) {
  const quests = useQuery({
    queryKey: ["character-quests", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/quests", { params: { path: { character_id: characterId } } })),
  });
  if (quests.isPending) return <Loading />;
  if (quests.error) return <ErrorText error={quests.error} />;
  return (
    <Routes>
      <Route index element={<Overview characterId={characterId} found={quests.data} />} />
      <Route path=":questId" element={<OneQuest characterId={characterId} />} />
    </Routes>
  );
}

function Overview({ characterId, found }: { characterId: string; found: CharacterQuestsOut }) {
  const dates = useDates();
  const withdraw = useAction((id: string) => unwrap(api.POST("/api/quest-requests/{request_id}/withdraw", { params: { path: { request_id: id } } })));
  const ongoing = found.quests.filter((q) => q.status === "active");
  const past = found.quests.filter((q) => q.status !== "active");
  return (
    <div className="flex flex-col gap-4">
      {found.limit > 0 || found.requests.length > 0 ? <Ask characterId={characterId} found={found} /> : null}
      {found.requests.length > 0 && (
        <Card title="Your requests">
          <ul className="flex flex-col gap-3">
            {found.requests.map((r) => (
              <li key={r.id} aria-label="Quest request" className="rounded-md border border-ash p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <time dateTime={r.created_at} className="text-mist">
                    {dates.dateTime(r.created_at)}
                  </time>
                  <Badge tone={r.status === "answered" ? "gold" : "mist"}>
                    {requestStatus(r.status)}
                    {r.status === "answered" && r.outcome !== "quest" ? `: ${outcomeText(r.outcome)}` : ""}
                  </Badge>
                </div>
                <p className="mt-1 whitespace-pre-line">{r.objective}</p>
                {r.note && <p className="mt-1 text-mist">From the storytellers: {r.note}</p>}
                {r.quest_id && (
                  <p className="mt-1">
                    <Link to={r.quest_id} className="text-gold hover:text-parchment">
                      See the quest
                    </Link>
                  </p>
                )}
                {r.can_withdraw && (
                  <Button variant="ghost" className="mt-1 min-h-8 px-2" onClick={() => withdraw.mutate(r.id)}>
                    Withdraw
                  </Button>
                )}
              </li>
            ))}
          </ul>
          <ErrorText error={withdraw.error} />
        </Card>
      )}
      <Card title="Quests">
        {found.quests.length === 0 ? (
          <Empty>No quests yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {[...ongoing, ...past].map((q) => (
              <QuestRow key={q.id} quest={q} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function QuestRow({ quest: q }: { quest: PlayerQuestOut }) {
  return (
    <li className="rounded-md border border-ash p-3 text-sm">
      <Link to={q.id} className="text-gold hover:text-parchment">
        {q.name}
      </Link>{" "}
      <span className="text-mist">
        · {questType(q)} · {questStatus(q.status)} · {roleText(q.role)}
      </span>
    </li>
  );
}

function Ask({ characterId, found }: { characterId: string; found: CharacterQuestsOut }) {
  const [kind, setKind] = useState<RequestKind>("custom");
  const [objective, setObjective] = useState("");
  const [reason, setReason] = useState("");
  const [companions, setCompanions] = useState("");
  const [place, setPlace] = useState({ name: "", address: "", map_link: "" });
  const [locationId, setLocationId] = useState("");
  const [quality, setQuality] = useState("");
  const [detail, setDetail] = useState("");
  const [harm, setHarm] = useState("");
  const [victory, setVictory] = useState("");
  const [target, setTarget] = useState("");
  const held = useQuery({
    queryKey: ["held-locations", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/held-locations", { params: { path: { character_id: characterId } } })),
    enabled: !found.refusal,
  });
  const reset = () => {
    setObjective("");
    setReason("");
    setCompanions("");
    setPlace({ name: "", address: "", map_link: "" });
    setLocationId("");
    setQuality("");
    setDetail("");
    setHarm("");
    setVictory("");
    setTarget("");
  };
  const ask = useAction(async () => {
    const path = { params: { path: { character_id: characterId } } };
    if (kind === "custom") {
      await unwrap(api.POST("/api/characters/{character_id}/quest-requests", { ...path, body: { objective, reason, companions } }));
    } else {
      const infiltrate = harm === "infiltrate";
      await unwrap(
        api.POST("/api/characters/{character_id}/location-requests", {
          ...path,
          body: {
            kind,
            ...place,
            location_id: locationId || null,
            quality,
            detail,
            negative: kind === "undermine" && !infiltrate ? harm : "",
            victory: infiltrate ? victory : "",
            target,
            reason,
          },
        }),
      );
    }
    reset();
  });
  const when = found.cycle_name ? ` in ${found.cycle_name}` : " until the next downtime cycle";
  const own = held.data?.locations ?? [];
  const wanted = held.data?.qualities.find((q) => q.name === quality);
  const ownLocation = (
    <Field label="Which of your locations">
      <Select required value={locationId} onChange={(e) => setLocationId(e.target.value)}>
        <option value="">Choose a location</option>
        {own.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
      </Select>
    </Field>
  );
  const why = (
    <Field label="Why (optional)">
      <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
    </Field>
  );
  return (
    <Card title="Ask for a quest">
      <p className="mb-3 text-sm text-mist">
        {found.used} of {found.limit} {found.limit === 1 ? "request" : "requests"} made{when}. A request the storytellers answer as not needed doesn't count.
      </p>
      {found.refusal ? (
        <Notice>{found.refusal}</Notice>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            ask.mutate(undefined);
          }}
        >
          <Field label="What kind of request">
            <Select value={kind} onChange={(e) => setKind(e.target.value as RequestKind)}>
              {REQUEST_KINDS.filter((k) => (k.value === "quality" || k.value === "repair" ? own.length > 0 : true)).map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Field>
          {kind === "custom" && (
            <>
              <Field label="What do you want to achieve?">
                <Textarea rows={3} required value={objective} onChange={(e) => setObjective(e.target.value)} />
              </Field>
              {why}
              <Field label="Characters you want to bring (optional)">
                <Textarea rows={1} value={companions} onChange={(e) => setCompanions(e.target.value)} />
              </Field>
            </>
          )}
          {(kind === "acquire" || kind === "undermine") && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name of the place">
                <Input required value={place.name} onChange={(e) => setPlace({ ...place, name: e.target.value })} />
              </Field>
              <Field label="Address" hint={kind === "undermine" ? "Your character must know it: have been there, or have its address." : undefined}>
                <Input value={place.address} onChange={(e) => setPlace({ ...place, address: e.target.value })} />
              </Field>
              {kind === "acquire" && (
                <Field label="Map link (optional)">
                  <Input type="url" value={place.map_link} onChange={(e) => setPlace({ ...place, map_link: e.target.value })} />
                </Field>
              )}
            </div>
          )}
          {kind === "quality" && (
            <>
              {ownLocation}
              <Field label="The quality you want" hint={wanted?.text}>
                <Select required value={quality} onChange={(e) => setQuality(e.target.value)}>
                  <option value="">Choose a quality</option>
                  {held.data?.qualities.map((q) => (
                    <option key={q.name} value={q.name}>
                      {q.name}
                    </option>
                  ))}
                </Select>
              </Field>
              {wanted?.detail && (
                <Field label={wanted.detail}>
                  <Input value={detail} onChange={(e) => setDetail(e.target.value)} />
                </Field>
              )}
            </>
          )}
          {kind === "undermine" && (
            <>
              <Field label="What you want to do to it">
                <Select required value={harm} onChange={(e) => setHarm(e.target.value)}>
                  <option value="">Choose</option>
                  {NEGATIVES.map((n) => (
                    <option key={n} value={n}>
                      Make it {n}
                    </option>
                  ))}
                  <option value="infiltrate">Infiltrate it</option>
                </Select>
              </Field>
              {harm === "infiltrate" && (
                <Field label="What getting in is for" hint="One goal: steal something, plant something, or rescue someone.">
                  <Input required value={victory} onChange={(e) => setVictory(e.target.value)} />
                </Field>
              )}
            </>
          )}
          {kind === "repair" && ownLocation}
          {kind === "whose" && (
            <Field label="Whose locations" hint="It expends a dot of your character's Contacts.">
              <Input required value={target} onChange={(e) => setTarget(e.target.value)} placeholder="A character's name" />
            </Field>
          )}
          {kind !== "custom" && kind !== "whose" && why}
          <div>
            <Button type="submit" disabled={ask.isPending}>
              Ask for this quest
            </Button>
          </div>
        </form>
      )}
      <ErrorText error={ask.error} />
    </Card>
  );
}

function OneQuest({ characterId }: { characterId: string }) {
  const { questId = "" } = useParams();
  const path = { params: { path: { character_id: characterId, quest_id: questId } } };
  const quest = useQuery({
    queryKey: ["character-quest", characterId, questId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/quests/{quest_id}", path)),
  });
  const join = useAction(() => unwrap(api.POST("/api/characters/{character_id}/quests/{quest_id}/join", path)));
  if (quest.isPending) return <Loading />;
  if (quest.error) return <ErrorText error={quest.error} />;
  const q = quest.data;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">
        <Link to=".." relative="path" className="text-mist hover:text-parchment">
          ← All quests
        </Link>
      </p>
      <Card title={q.name} actions={<Badge tone={q.status === "active" ? "gold" : q.status === "completed" ? "gold" : "mist"}>{questStatus(q.status)}</Badge>}>
        <div className="flex flex-col gap-2 text-sm">
          <p className="text-mist">
            {questType(q)} · {roleText(q.role)} · Leader: {q.leader_name ?? "no one yet"}
          </p>
          {q.objective && <p className="whitespace-pre-line">{q.objective}</p>}
          {q.party.length > 0 && <p className="text-mist">The party: {q.party.join(", ")}</p>}
          {q.status === "closed" && <Notice>Closed by the storytellers: {q.close_note}</Notice>}
          {q.ended_on && (
            <p>
              {questStatus(q.status)} on {q.ended_on}, by {q.finished_by.join(", ")}.
            </p>
          )}
          {q.can_join && (
            <div>
              <Button onClick={() => join.mutate(undefined)} disabled={join.isPending}>
                Join this quest
              </Button>
            </div>
          )}
          <ErrorText error={join.error} />
        </div>
      </Card>
      <Card title="Requirements">
        <p className="mb-2 text-sm text-mist">The party meets these, or others help as patrons, before the quest's scenarios.</p>
        <ul className="flex flex-col gap-1 text-sm">
          {q.requirements.map((r, i) => (
            <li key={i}>
              {r.met ? "✓" : "○"} {r.label}
              {r.met && <span className="text-mist"> (met by {r.met_by_name})</span>}
            </li>
          ))}
        </ul>
      </Card>
      {q.results.length > 0 && (
        <Card title="Results">
          <ol className="flex flex-col gap-3">
            {q.results.map((r) => (
              <li key={r.number} className="text-sm">
                <p className="text-gold">{resultText(r)}</p>
                <RichText text={r.text} />
              </li>
            ))}
          </ol>
          <p className="mt-2 text-xs text-mist">
            {q.results.length} of {q.scenario_count} {q.scenario_count === 1 ? "scenario" : "scenarios"} done.
          </p>
        </Card>
      )}
      {q.can_share && <Share characterId={characterId} questId={q.id} />}
      {(q.status === "completed" || q.status === "failed") && (q.can_write_tale || q.tale) && <Tale characterId={characterId} quest={q} />}
    </div>
  );
}

function Share({ characterId, questId }: { characterId: string; questId: string }) {
  const path = { params: { path: { character_id: characterId, quest_id: questId } } };
  const [who, setWho] = useState("");
  const choices = useQuery({
    queryKey: ["quest-share-choices", characterId, questId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/quests/{quest_id}/share-choices", path)),
  });
  const share = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/quests/{quest_id}/share", { ...path, body: { character_ids: [who] } }));
    setWho("");
  });
  return (
    <Card title="Share it">
      <p className="mb-2 text-sm text-mist">Characters you share it with see its name, objective and requirements, and can join the party.</p>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          share.mutate(undefined);
        }}
      >
        <Field label="Share with">
          <Select required value={who} onChange={(e) => setWho(e.target.value)} className="w-auto">
            <option value="">Choose a character</option>
            {choices.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" disabled={!who || share.isPending}>
          Share
        </Button>
      </form>
      <ErrorText error={share.error ?? choices.error} />
    </Card>
  );
}

function Tale({ characterId, quest: q }: { characterId: string; quest: PlayerQuestOut }) {
  const [tale, setTale] = useState<string | null>(null);
  const save = useAction(async () => {
    await unwrap(
      api.PUT("/api/characters/{character_id}/quests/{quest_id}/tale", { params: { path: { character_id: characterId, quest_id: q.id } }, body: { tale: tale ?? q.tale, approve: false } }),
    );
    setTale(null);
  });
  return (
    <Card title="Telling the Tale" actions={q.tale_approved ? <Badge tone="gold">Approved</Badge> : q.tale ? <Badge>Waiting for approval</Badge> : null}>
      {q.can_write_tale ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <p className="text-sm text-mist">Write what happened on the quest, together with the party; the storytellers approve it as the official account.</p>
          <Field label="The tale">
            <Textarea rows={5} value={tale ?? q.tale} onChange={(e) => setTale(e.target.value)} />
          </Field>
          <div>
            <Button type="submit" disabled={save.isPending}>
              Save the tale
            </Button>
          </div>
          <ErrorText error={save.error} />
        </form>
      ) : (
        <RichText text={q.tale} />
      )}
    </Card>
  );
}
