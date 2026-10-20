import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, DifferenceOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { describeDifference, settlementLabel } from "../../settlements";


export function TroupesTab({ character }: { character: CharacterOut }) {
  const path = { params: { path: { character_id: character.id } } };
  const memberships = useQuery({
    queryKey: ["memberships", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/troupes", path)),
  });
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const sheet = useQuery({
    queryKey: ["sheet", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", path)),
  });
  const [joining, setJoining] = useState("");

  const join = useAction((troupe_id: string) => unwrap(api.POST("/api/characters/{character_id}/troupes", { ...path, body: { troupe_id } })));
  const leave = useAction((troupe_id: string) =>
    unwrap(api.DELETE("/api/characters/{character_id}/troupes/{troupe_id}", { params: { path: { character_id: character.id, troupe_id } } })),
  );
  const withdraw = useAction(() => unwrap(api.DELETE("/api/characters/{character_id}/home-troupe", path)));

  if (memberships.isPending || troupes.isPending || sheet.isPending) return <Loading />;
  const memberIds = new Set(memberships.data?.map((m) => m.troupe_id));
  const pendingHome = sheet.data?.pending_approvals.find((a) => a.kind === "home_troupe_change") ?? null;
  const pendingTroupe = troupes.data?.find((t) => t.id === pendingHome?.troupe_id);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Troupes">
        {memberships.data?.length ? (
          <ul className="divide-y divide-ash">
            {memberships.data.map((m) => (
              <li key={m.troupe_id} className="flex items-center justify-between gap-2 py-2">
                <span className="flex flex-wrap items-center gap-2">
                  {m.troupe_name}
                  {m.home ? <Badge tone="gold">home</Badge> : <Badge>visiting</Badge>}
                </span>
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (window.confirm(`Take ${character.name} out of ${m.troupe_name}? Its storytellers will see that it left.`))
                      leave.mutate(m.troupe_id);
                  }}
                >
                  Leave
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            Not in any troupe. A character plays in its one home troupe, and can visit others; joining a troupe as a visitor lets
            its storytellers see the sheet.
          </Empty>
        )}
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (joining) join.mutate(joining);
          }}
        >
          <Select value={joining} onChange={(e) => setJoining(e.target.value)} aria-label="Troupe to join">
            <option value="">Visit a troupe…</option>
            {troupes.data
              ?.filter((t) => !memberIds.has(t.id))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
          </Select>
          <Button type="submit" variant="secondary" disabled={!joining}>
            Visit
          </Button>
        </form>
        <ErrorText error={join.error ?? leave.error} />
      </Card>

      {pendingHome ? (
        <Card title="Home troupe">
          <p className="text-sm">
            Waiting for {pendingTroupe?.name ?? "the troupe"}'s storytellers to accept this character.
          </p>
          <Button variant="secondary" className="mt-3" onClick={() => withdraw.mutate(undefined)}>
            Withdraw the request
          </Button>
          <ErrorText error={withdraw.error} />
        </Card>
      ) : (
        character.creation_complete ? (
          <HomeTroupe
            character={character}
            troupes={troupes.data ?? []}
            currentHome={character.home_troupe_id}
            unbanked={sheet.data?.xp.unbanked ?? 0}
          />
        ) : (
          <Card title="Home troupe">
            <Notice>Finish character creation on the Sheet tab before choosing a home troupe.</Notice>
          </Card>
        )
      )}
    </div>
  );
}

function HomeTroupe({
  character,
  troupes,
  currentHome,
  unbanked,
}: {
  character: CharacterOut;
  troupes: { id: string; name: string }[];
  currentHome: string | null;
  /** Creation XP lost if a first home troupe accepts the character now. */
  unbanked: number;
}) {
  const path = { params: { path: { character_id: character.id } } };
  const [troupeId, setTroupeId] = useState("");
  const [differences, setDifferences] = useState<DifferenceOut[] | null>(null);
  const [settlements, setSettlements] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const key = (d: DifferenceOut) => `${d.difference === "creation_differs"}/${d.category}/${d.name}/${d.detail}`;

  const preview = useAction(async (troupe_id: string) => {
    const found = await unwrap(api.POST("/api/characters/{character_id}/home-troupe/preview", { ...path, body: { troupe_id } }));
    setDifferences(found);
    setSettlements(Object.fromEntries(found.map((d) => [key(d), d.allowed_settlements[0] ?? "keep_price"])));
  });
  const request = useAction(() =>
    unwrap(
      api.POST("/api/characters/{character_id}/home-troupe", {
        ...path,
        body: {
          troupe_id: troupeId,
          note,
          settlements: (differences ?? []).map((d) => ({
            category: d.category,
            name: d.name,
            detail: d.detail,
            difference: d.difference,
            settlement: settlements[key(d)] as DifferenceOut["allowed_settlements"][number],
          })),
        },
      }),
    ),
  );

  return (
    <Card title="Home troupe">
      <p className="mb-3 text-sm text-mist">
        Your home troupe runs this character's downtimes, and its house rules set what traits cost. Its storytellers must
        accept the move.
      </p>
      <Field label="Troupe">
        <Select
          value={troupeId}
          onChange={(e) => {
            setTroupeId(e.target.value);
            setDifferences(null);
            if (e.target.value) preview.mutate(e.target.value);
          }}
        >
          <option value="">Choose…</option>
          {troupes
            .filter((t) => t.id !== currentHome)
            .map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
        </Select>
      </Field>
      <ErrorText error={preview.error} />
      {differences && (
        <div className="mt-4 flex flex-col gap-3">
          {differences.length === 0 ? (
            <Notice>Nothing differs: this troupe's rules price the sheet as you paid for it.</Notice>
          ) : (
            <>
              <p className="text-sm">This troupe's rules differ from what you built with. Say how to settle each one:</p>
              {differences.map((d) => (
                <Field key={key(d)} label={`${d.name}${d.detail ? `: ${d.detail}` : ""} — ${describeDifference(d)}`}>
                  <Select value={settlements[key(d)]} onChange={(e) => setSettlements({ ...settlements, [key(d)]: e.target.value })}>
                    {d.allowed_settlements.map((s) => (
                      <option key={s} value={s}>
                        {settlementLabel(s, d)}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </>
          )}
          {unbanked > 0 && (
            <Notice>
              Only 5 unspent creation XP carry over once a home troupe accepts {character.name}. If accepted now, {unbanked} XP will
              be lost; spend it first if you want it.
            </Notice>
          )}
          <Field label="A note for the storytellers">
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Button onClick={() => request.mutate(undefined)} disabled={request.isPending}>
            Ask to join as home troupe
          </Button>
          <ErrorText error={request.error} />
        </div>
      )}
    </Card>
  );
}
