import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, DifferenceOut } from "../../api/types";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

const SETTLEMENT_LABELS: Record<string, string> = {
  pay_difference: "Pay the difference",
  refund_difference: "Refund the difference",
  keep_price: "Keep the price I paid",
  remove_and_refund: "Remove it and refund me",
};

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
  const pendingHome = sheet.data?.pending_approval?.kind === "home_troupe_change" ? sheet.data.pending_approval : null;
  const pendingTroupe = troupes.data?.find((t) => t.id === pendingHome?.troupe_id);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card title="Troupes">
        {memberships.data?.length ? (
          <ul className="divide-y divide-ash">
            {memberships.data.map((m) => (
              <li key={m.troupe_id} className="flex items-center justify-between gap-2 py-2">
                <span>
                  {m.troupe_name} {m.home && <Badge tone="gold">home</Badge>}
                </span>
                <Button variant="ghost" onClick={() => leave.mutate(m.troupe_id)}>
                  Leave
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>Not in any troupe. Joining one lets its storytellers see this sheet.</Empty>
        )}
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (joining) join.mutate(joining);
          }}
        >
          <Select value={joining} onChange={(e) => setJoining(e.target.value)} aria-label="Troupe to join">
            <option value="">Join a troupe…</option>
            {troupes.data
              ?.filter((t) => !memberIds.has(t.id))
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
          </Select>
          <Button type="submit" variant="secondary" disabled={!joining}>
            Join
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
        <HomeTroupe character={character} troupes={troupes.data ?? []} currentHome={character.home_troupe_id} />
      )}
    </div>
  );
}

function HomeTroupe({ character, troupes, currentHome }: { character: CharacterOut; troupes: { id: string; name: string }[]; currentHome: string | null }) {
  const path = { params: { path: { character_id: character.id } } };
  const [troupeId, setTroupeId] = useState("");
  const [differences, setDifferences] = useState<DifferenceOut[] | null>(null);
  const [settlements, setSettlements] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const key = (d: DifferenceOut) => `${d.category}/${d.name}/${d.detail}`;

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
              <p className="text-sm">These traits cost differently there. Say how to settle each one:</p>
              {differences.map((d) => (
                <Field
                  key={key(d)}
                  label={`${d.name}${d.detail ? `: ${d.detail}` : ""} — paid ${d.old_cost}, ${d.difference === "not_allowed" ? "not allowed there" : `costs ${d.new_cost} there`}`}
                >
                  <Select value={settlements[key(d)]} onChange={(e) => setSettlements({ ...settlements, [key(d)]: e.target.value })}>
                    {d.allowed_settlements.map((s) => (
                      <option key={s} value={s}>
                        {SETTLEMENT_LABELS[s]}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </>
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
