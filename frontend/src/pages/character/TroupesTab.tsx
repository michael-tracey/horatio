import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, DifferenceOut, XpStandingOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { InfoButton } from "../../components/InfoButton";
import { Button, Card, ErrorText, Field, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { describeDifference, settlementLabel } from "../../settlements";


const HOME_MEANS =
  "The one troupe that holds this character's sheet. It accepts the character, awards its XP, approves its discipline purchases, sets what traits cost with its house rules, and runs its downtimes.";
const VISITING_MEANS =
  "A troupe this character plays in without its home there. Its storytellers can see the sheet, but approve nothing on it and award it no XP. A character can visit several.";

/** What a home troupe is, beside the card's title rather than above what it holds. */
const homeInfo = (
  <InfoButton label="What a home troupe is">
    <span className="block">{HOME_MEANS}</span>
    <span className="mt-1 block">A character has at most one, and its storytellers must accept the move.</span>
  </InfoButton>
);

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
  const visits = memberships.data?.filter((m) => !m.home) ?? [];
  const pendingHome = sheet.data?.pending_approvals.find((a) => a.kind === "home_troupe_change") ?? null;
  const pendingTroupe = troupes.data?.find((t) => t.id === pendingHome?.troupe_id);
  const homeName = memberships.data?.find((m) => m.home)?.troupe_name ?? troupes.data?.find((t) => t.id === character.home_troupe_id)?.name ?? null;
  const buildingFor = troupes.data?.find((t) => t.id === character.building_troupe_id)?.name;
  // The card opens with where the character's home is now, whatever else it holds.
  const homeNow =
    character.home_troupe_id && homeName ? (
      <HomeNow troupeId={character.home_troupe_id} name={homeName} />
    ) : (
      <p className="mb-2 text-lg text-parchment">No home troupe yet</p>
    );

  return (
    <div className="grid gap-6 md:grid-cols-2">
      {pendingHome ? (
        <Card title="Home troupe" info={homeInfo}>
          {homeNow}
          <p className="text-sm">
            Waiting for {pendingTroupe?.name ?? "the troupe"}'s storytellers to accept this character.
          </p>
          <p className="mt-1 text-sm text-mist">Nothing for you to do until they decide.</p>
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
            homeNow={homeNow}
            unbanked={sheet.data?.xp.unbanked ?? 0}
          />
        ) : (
          <Card title="Home troupe" info={homeInfo}>
            {homeNow}
            <p className="text-sm text-mist">
              Finish creating {character.name} on the{" "}
              <Link to={`/characters/${character.id}/create`} className="text-gold underline">
                Create tab
              </Link>{" "}
              first, then ask {buildingFor ?? "a troupe"} here to make it {character.name}'s home.
            </p>
          </Card>
        )
      )}

      <Card title="Visiting troupes" info={<InfoButton label="What a visiting troupe is">{VISITING_MEANS}</InfoButton>}>
        {visits.length ? (
          <ul className="divide-y divide-ash">
            {visits.map((m) => (
              <li key={m.troupe_id} className="flex items-center justify-between gap-2 py-2">
                <span>{m.troupe_name}</span>
                <span className="flex items-center gap-1">
                  <HouseRulesLink troupeId={m.troupe_id} name={m.troupe_name} />
                  <Button
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm(`Take ${character.name} out of ${m.troupe_name}? Its storytellers will see that it left.`))
                        leave.mutate(m.troupe_id);
                    }}
                  >
                    Leave
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="Not visiting any troupe.">To play at another troupe's games without making it home, choose it below.</EmptyState>
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

    </div>
  );
}

/** Where the character's home is now, first in the card, with what it plays differently. */
function HomeNow({ troupeId, name }: { troupeId: string; name: string }) {
  return (
    <p className="mb-2 flex flex-wrap items-baseline gap-x-2">
      <span className="text-lg text-parchment">
        <span className="text-mist">Home now:</span> {name}
      </span>
      <HouseRulesLink troupeId={troupeId} name={name} />
    </p>
  );
}

function HomeTroupe({
  character,
  troupes,
  currentHome,
  homeNow,
  unbanked,
}: {
  character: CharacterOut;
  troupes: { id: string; name: string }[];
  currentHome: string | null;
  /** Where its home is now, which the card opens with. */
  homeNow: ReactNode;
  /** Creation XP lost if a first home troupe accepts the character now. */
  unbanked: number;
}) {
  const path = { params: { path: { character_id: character.id } } };
  // A troupe's "Play here" card links here with ?home=<id>, to ask that troupe at once.
  const [params] = useSearchParams();
  const asked = params.get("home");
  const [troupeId, setTroupeId] = useState(troupes.some((t) => t.id === asked && t.id !== currentHome) ? asked! : "");
  // With a home already, choosing another waits behind a button: most visits here are to see where it is.
  const [moving, setMoving] = useState(!currentHome || !!troupeId);
  const [differences, setDifferences] = useState<DifferenceOut[] | null>(null);
  const [settlements, setSettlements] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [standing, setStanding] = useState<XpStandingOut | null>(null);
  const [topUp, setTopUp] = useState(true);
  const key = (d: DifferenceOut) => `${d.difference === "creation_differs"}/${d.category}/${d.name}/${d.detail}`;

  const preview = useAction(async (troupe_id: string) => {
    const [found, xp] = await Promise.all([
      unwrap(api.POST("/api/characters/{character_id}/home-troupe/preview", { ...path, body: { troupe_id } })),
      unwrap(api.POST("/api/characters/{character_id}/home-troupe/xp-preview", { ...path, body: { troupe_id } })),
    ]);
    setStanding(xp);
    setDifferences(found);
    setSettlements(Object.fromEntries(found.map((d) => [key(d), d.allowed_settlements[0] ?? "keep_price"])));
  });
  // Show what moving to the troupe the link chose means, as choosing it would.
  useEffect(() => {
    if (troupeId) preview.mutate(troupeId);
    // Only for the troupe the page opened with; choosing another previews it on change.
  }, []);
  const request = useAction(() =>
    unwrap(
      api.POST("/api/characters/{character_id}/home-troupe", {
        ...path,
        body: {
          troupe_id: troupeId,
          note,
          top_up: topUp,
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

  if (!moving)
    return (
      <Card title="Home troupe" info={homeInfo}>
        {homeNow}
        <Button variant="secondary" onClick={() => setMoving(true)}>
          Move to another troupe…
        </Button>
      </Card>
    );

  return (
    <Card title="Home troupe" info={homeInfo}>
      {homeNow}
      {!currentHome && (
        <p className="mb-3 text-sm text-mist">Choose the troupe {character.name} will play in. Its storytellers decide whether to accept it.</p>
      )}
      <Field label={currentHome ? "New home troupe" : "Troupe"}>
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
      {troupeId && <HouseRulesLink troupeId={troupeId} name={troupes.find((t) => t.id === troupeId)?.name ?? "the troupe"} />}
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
          {standing && <XpStanding standing={standing} topUp={topUp} onTopUp={setTopUp} />}
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

/** A link to a troupe's house rules: what it plays differently from the book. */
function HouseRulesLink({ troupeId, name }: { troupeId: string; name: string }) {
  return (
    <Link
      to={`/troupes/${troupeId}/house-rules`}
      aria-label={`${name}'s house rules`}
      className="inline-flex min-h-8 items-center px-2 text-sm text-mist underline hover:text-parchment"
    >
      House rules
    </Link>
  );
}

/** The character's XP against the troupe's floor and ceiling, and the top-up below the floor. */
function XpStanding({ standing: s, topUp, onTopUp }: { standing: XpStandingOut; topUp: boolean; onTopUp: (on: boolean) => void }) {
  const below = s.floor - s.given;
  const above = s.given - s.ceiling;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-ash px-3 py-2 text-sm">
      <p>
        This troupe's XP floor is {s.floor} and its ceiling {s.ceiling}. This character has been given {s.given} XP
        {s.self_entered > 0 && <>, {s.self_entered} of it self-entered</>}.
      </p>
      {below > 0 && (
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={topUp} onChange={(e) => onTopUp(e.target.checked)} />
          Top up to the floor: {below} XP more{s.self_entered > 0 && " (more if the storytellers remove self-entered XP)"}
        </label>
      )}
      {above > 0 && <p className="text-gold">That is {above} XP above the ceiling. The storytellers will see it, and decide whether it stays.</p>}
      {s.self_entered > 0 && <p className="text-mist">The storytellers see self-entered XP apart, and accept or remove it.</p>}
    </div>
  );
}
