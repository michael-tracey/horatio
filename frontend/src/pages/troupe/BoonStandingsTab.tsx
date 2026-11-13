import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BoonStandingsOut, BoonWeightsIn } from "../../api/types";
import { BOON_PAGE, KINDS, kindName } from "../../boons";
import { DEFAULT_WEIGHTS, months, net, netWords, SCOPES, share, weight, weightsLine, type Scope } from "../../boonStandings";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

type Standings = BoonStandingsOut;
type Party = Standings["characters"][number]["who"];
type Group = Standings["clans"][number];
type Tally = Standings["court"][number]["owe_them"][number];

/** How many characters the standing list shows before "Show everyone". */
const FIRST = 25;

/**
 * Boon standings (#691), for the troupe's running staff: where everyone stands in its
 * boon ledger, live. Every kind has a weight (the troupe's own, or Trivial 0.5, Minor
 * 1, Major 3, Blood 5, Life 10), and a character's net is the weight owed to them less
 * the weight they owe. Tables first, each with a plain bar beside the numbers; the
 * charts come with #702. Only shown while the troupe keeps a ledger. With `harpy`, as
 * the Harpy reads them from their ledger page where the troupe allows it (#749): who
 * has left only as the court knows it (the server sees to that), and the weights read
 * only.
 */
export function BoonStandingsTab({ troupeId, harpy = false }: { troupeId: string; harpy?: boolean }) {
  const [scope, setScope] = useState<Scope>("active");
  const standings = useQuery({
    queryKey: ["boon-standings", troupeId, scope],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/boon-standings", {
          params: { path: { troupe_id: troupeId }, query: { scope } },
        }),
      ),
    placeholderData: (previous) => previous,
  });
  if (standings.isPending) return <Loading />;
  if (standings.error) return <ErrorText error={standings.error} />;
  const s = standings.data;
  const { trivial, minor, major, blood, life } = s.weights;
  const weights: BoonWeightsIn = { trivial, minor, major, blood, life };
  return (
    <div className="flex flex-col gap-4">
      <Card title="Boon standings">
        <p className="mb-3 text-sm text-mist">
          Where everyone stands in the boon ledger, now ({BOON_PAGE}). Each kind of boon has a weight, and a character&apos;s <strong>net</strong> is the weight
          owed to them less the weight they owe.{" "}
          {harpy ? (
            <>Who has left is shown as the court knows it.</>
          ) : (
            <>
              The boons themselves are on the <Link to={`/troupes/${troupeId}/boons`}>Ledger</Link>.
            </>
          )}
        </p>
        <fieldset className="flex flex-wrap items-center gap-2 text-sm">
          <legend className="sr-only">Who is counted</legend>
          {SCOPES.map((o) => (
            <label key={o.value} className="flex items-center gap-1" title={o.meaning}>
              <input type="radio" name="boon-standings-scope" checked={scope === o.value} onChange={() => setScope(o.value)} />
              {o.label}
            </label>
          ))}
          <span className="text-xs text-mist">{SCOPES.find((o) => o.value === scope)?.meaning}</span>
        </fieldset>
        <Totals totals={s.totals} />
        {harpy ? (
          <p className="mt-3 text-sm">
            <span className="text-mist">Weights{s.weights.defaults ? " (the defaults)" : ""}:</span> {weightsLine(weights)}
          </p>
        ) : (
          <Weights troupeId={troupeId} weights={weights} defaults={s.weights.defaults} />
        )}
      </Card>
      <ByKind standings={s} />
      <Characters standings={s} />
      <Court standings={s} />
      <Groups title="By clan" groups={s.clans} label="Clan" />
      <Groups title="By age" groups={s.ages} label="Age" />
      <Groups title="By sect" groups={s.sects} label="Sect" />
      <DebtAge standings={s} />
      <Settling standings={s} />
      <Across title="Across clan lines" across={s.across_clans} line="clan" />
      <Across title="Across sect lines" across={s.across_sects} line="sect" />
      <Mutual standings={s} />
    </div>
  );
}

function Totals({ totals }: { totals: Standings["totals"] }) {
  const tiles: [string, number, string][] = [
    ["Open", totals.open, "Standing, with everyone on them in play."],
    ["Involve the departed", totals.departed, "Standing, but someone on them is dead or off-field."],
    ["Settled", totals.settled, "Called in, forgiven or formally ignored."],
    ["Waiting for review", totals.pending, "Submitted, not yet registered."],
    ["Name only", totals.name_only, "Standing boons with a side not linked to a character."],
  ];
  return (
    <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5" aria-label="The whole ledger">
      {tiles.map(([label, value, meaning]) => (
        <div key={label} className="rounded border border-ash px-3 py-2" title={meaning}>
          <dt className="text-xs text-mist">{label}</dt>
          <dd className="text-xl text-parchment tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Weights({ troupeId, weights, defaults }: { troupeId: string; weights: BoonWeightsIn; defaults: boolean }) {
  const toast = useToast();
  const [editing, setEditing] = useState<Record<keyof BoonWeightsIn, string> | null>(null);
  const save = useAction(async (next: BoonWeightsIn) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-weights", { params: { path: { troupe_id: troupeId } }, body: next }));
    setEditing(null);
    toast({ message: "The boon weights are saved." });
  });
  const start = (from: BoonWeightsIn) =>
    setEditing({
      trivial: String(from.trivial),
      minor: String(from.minor),
      major: String(from.major),
      blood: String(from.blood),
      life: String(from.life),
    });
  return (
    <div className="mt-3 text-sm">
      <p>
        <span className="text-mist">Weights{defaults ? " (the defaults)" : ""}:</span> {weightsLine(weights)}{" "}
        {!editing && (
          <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => start(weights)}>
            Change
          </button>
        )}
      </p>
      {editing && (
        <form
          className="mt-2 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({
              trivial: Number(editing.trivial),
              minor: Number(editing.minor),
              major: Number(editing.major),
              blood: Number(editing.blood),
              life: Number(editing.life),
            });
          }}
        >
          {KINDS.map((k) => (
            <div key={k.value} className="w-20">
              <Field label={k.label}>
                <Input
                  type="number"
                  min={0.25}
                  max={100}
                  step={0.25}
                  required
                  value={editing[k.value]}
                  onChange={(e) => setEditing({ ...editing, [k.value]: e.target.value })}
                />
              </Field>
            </div>
          ))}
          <Button type="submit" disabled={save.isPending}>
            Save weights
          </Button>
          <Button type="button" variant="ghost" onClick={() => start(DEFAULT_WEIGHTS)}>
            Defaults
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      )}
    </div>
  );
}

/** A plain bar for one measure, in gold; the number is always beside it. */
function Bar({ value, most, label }: { value: number; most: number; label: string }) {
  return (
    <div className="h-2 w-full min-w-16 rounded bg-ash/60" title={label} aria-hidden="true">
      <div className="h-full rounded bg-gold" style={{ width: `${share(value, most)}%` }} />
    </div>
  );
}

/**
 * A net, as a bar from a middle line: right in gold for owed more than they owe, left
 * in mist for owing more. Its sign is in its position and in the number beside it,
 * never in its colour alone (gold and blood are too close in Ultra goth).
 */
function NetBar({ value, most }: { value: number; most: number }) {
  const half = share(Math.abs(value), most) / 2;
  return (
    <div className="relative h-2 w-full min-w-20" title={netWords(value)} aria-hidden="true">
      <div className="absolute inset-y-[-2px] left-1/2 w-px bg-line" />
      {value > 0 && <div className="absolute inset-y-0 left-1/2 rounded-r bg-gold" style={{ width: `${half}%` }} />}
      {value < 0 && <div className="absolute inset-y-0 right-1/2 rounded-l bg-mist" style={{ width: `${half}%` }} />}
    </div>
  );
}

function Table({ label, head, children }: { label: string; head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label={label}>
        <thead className="text-left text-xs text-mist">{head}</thead>
        <tbody className="divide-y divide-ash/60">{children}</tbody>
      </table>
    </div>
  );
}

const num = "px-2 py-1 text-right tabular-nums";
const cell = "px-2 py-1";

function Name({ who }: { who: Party }) {
  const gone = who.standing && who.standing !== "active" && who.standing !== "inactive";
  return (
    <span>
      {who.name}
      {who.character_id === null && <span className="text-xs text-mist"> (name only)</span>}
      {gone && <span className="text-xs text-mist"> ({who.standing === "final_death" ? "Final Death" : who.standing === "off_field" ? "Off-field" : "retired"})</span>}
    </span>
  );
}

function ByKind({ standings }: { standings: Standings }) {
  const most = Math.max(0, ...standings.by_kind.map((k) => k.count));
  return (
    <Card title="Open boons by kind">
      <Table
        label="Open boons by kind"
        head={
          <tr>
            <th className={cell}>Kind</th>
            <th className={num}>Weight</th>
            <th className={num}>Open</th>
            <th className={num}>Total weight</th>
            <th className={cell}>
              <span className="sr-only">Bar</span>
            </th>
          </tr>
        }
      >
        {standings.by_kind.map((k) => (
          <tr key={k.kind}>
            <td className={cell}>{kindName(k.kind)}</td>
            <td className={num}>{weight(k.weight)}</td>
            <td className={num}>{k.count}</td>
            <td className={num}>{weight(k.total)}</td>
            <td className={`${cell} w-1/3`}>
              <Bar value={k.count} most={most} label={`${k.count} open`} />
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function Characters({ standings }: { standings: Standings }) {
  const [all, setAll] = useState(false);
  const rows = standings.characters;
  const shown = all ? rows : rows.slice(0, FIRST);
  const most = Math.max(0, ...rows.map((c) => Math.abs(c.net)));
  return (
    <Card title="Standing by character">
      {rows.length === 0 ? (
        <Empty>No open boons.</Empty>
      ) : (
        <>
          <Table
            label="Standing by character"
            head={
              <tr>
                <th className={cell}>Character</th>
                <th className={cell}>Clan</th>
                <th className={num}>Owes</th>
                <th className={num}>Owed</th>
                <th className={num}>Net</th>
                <th className={cell}>
                  <span className="sr-only">Bar</span>
                </th>
              </tr>
            }
          >
            {shown.map((c) => (
              <tr key={c.who.key}>
                <td className={cell}>
                  <Name who={c.who} />
                </td>
                <td className={`${cell} text-mist`}>{c.who.clan ?? ""}</td>
                <td className={num}>{weight(c.owes)}</td>
                <td className={num}>{weight(c.owed)}</td>
                <td className={num} aria-label={netWords(c.net)}>
                  {net(c.net)}
                </td>
                <td className={`${cell} w-1/4`}>
                  <NetBar value={c.net} most={most} />
                </td>
              </tr>
            ))}
          </Table>
          {rows.length > FIRST && (
            <button type="button" className="mt-2 text-xs text-mist underline hover:text-parchment" onClick={() => setAll(!all)}>
              {all ? `Show the first ${FIRST}` : `Show everyone (${rows.length})`}
            </button>
          )}
        </>
      )}
    </Card>
  );
}

function Tallies({ label, tallies }: { label: string; tallies: Tally[] }) {
  return (
    <div>
      <h4 className="text-xs text-mist">{label}</h4>
      {tallies.length === 0 ? (
        <p className="text-xs text-mist">Nobody.</p>
      ) : (
        <ul className="text-sm">
          {tallies.map((t) => (
            <li key={t.who.key} className="flex justify-between gap-2">
              <Name who={t.who} />
              <span className="text-mist tabular-nums">
                {t.count} · {weight(t.weight)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Court({ standings }: { standings: Standings }) {
  return (
    <Card title="The court">
      {standings.court.length === 0 ? (
        <Empty>No title holder has an open boon.</Empty>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {standings.court.map((o) => (
            <li key={`${o.title}:${o.standing.who.key}`} className="rounded border border-ash p-3">
              <h3 className="text-sm">
                <span className="text-gold">{o.title}</span> · <Name who={o.standing.who} />
              </h3>
              <p className="text-xs text-mist">
                Owed {weight(o.standing.owed)}, owes {weight(o.standing.owes)}, net <span aria-label={netWords(o.standing.net)}>{net(o.standing.net)}</span>
              </p>
              <div className="mt-2 grid grid-cols-2 gap-3">
                <Tallies label="Owe them most" tallies={o.owe_them} />
                <Tallies label="They owe most" tallies={o.they_owe} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Groups({ title, groups, label }: { title: string; groups: Group[]; label: string }) {
  const most = Math.max(0, ...groups.map((g) => Math.abs(g.net)));
  return (
    <Card title={title}>
      {groups.length === 0 ? (
        <Empty>No open boons.</Empty>
      ) : (
        <Table
          label={title}
          head={
            <tr>
              <th className={cell}>{label}</th>
              <th className={num}>Characters</th>
              <th className={num}>Owes</th>
              <th className={num}>Owed</th>
              <th className={num}>Net</th>
              <th className={cell}>
                <span className="sr-only">Bar</span>
              </th>
            </tr>
          }
        >
          {groups.map((g) => (
            <tr key={g.label}>
              <td className={cell}>{g.label}</td>
              <td className={num}>{g.characters}</td>
              <td className={num}>{weight(g.owes)}</td>
              <td className={num}>{weight(g.owed)}</td>
              <td className={num} aria-label={netWords(g.net)}>
                {net(g.net)}
              </td>
              <td className={`${cell} w-1/4`}>
                <NetBar value={g.net} most={most} />
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

function DebtAge({ standings }: { standings: Standings }) {
  const most = Math.max(0, ...standings.debt_age.map((b) => b.count));
  return (
    <Card title="Age of open debt">
      <p className="mb-2 text-xs text-mist">How long each open boon has stood, in months, from the night it was made.</p>
      <Table
        label="Age of open debt"
        head={
          <tr>
            <th className={cell}>Months</th>
            <th className={num}>Boons</th>
            <th className={num}>Weight</th>
            <th className={cell}>
              <span className="sr-only">Bar</span>
            </th>
          </tr>
        }
      >
        {standings.debt_age.map((b) => (
          <tr key={b.label}>
            <td className={cell}>{b.label}</td>
            <td className={num}>{b.count}</td>
            <td className={num}>{weight(b.weight)}</td>
            <td className={`${cell} w-1/2`}>
              <Bar value={b.count} most={most} label={`${b.count} boons`} />
            </td>
          </tr>
        ))}
      </Table>
    </Card>
  );
}

function Settling({ standings }: { standings: Standings }) {
  const s = standings.settling;
  return (
    <Card title="Settling">
      <p className="mb-2 text-sm">
        {s.count} settled, weighing {weight(s.weight)}; half were settled within {months(s.median_months)} of being made.
      </p>
      <Table
        label="Settled by kind"
        head={
          <tr>
            <th className={cell}>Kind</th>
            <th className={num}>Settled</th>
            <th className={num}>Called in</th>
            <th className={num}>Forgiven</th>
            <th className={num}>Ignored</th>
            <th className={num}>Typical time</th>
          </tr>
        }
      >
        {s.by_kind.map((k) => (
          <tr key={k.kind}>
            <td className={cell}>{kindName(k.kind)}</td>
            <td className={num}>{k.count}</td>
            <td className={num}>{k.called_in}</td>
            <td className={num}>{k.forgiven}</td>
            <td className={num}>{k.ignored}</td>
            <td className={num}>{months(k.median_months)}</td>
          </tr>
        ))}
      </Table>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <h3 className="text-xs text-mist">Settled by the debtor&apos;s clan</h3>
          <ul className="text-sm">
            {s.by_clan.map((b) => (
              <li key={b.label} className="flex justify-between gap-2">
                {b.label}
                <span className="text-mist tabular-nums">
                  {b.count} · {weight(b.weight)}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs text-mist">Call their boons in</h3>
          <ul className="text-sm">
            {s.calls_in.map((c) => (
              <li key={c.who.key} className="flex justify-between gap-2" title={`Called in ${weight(c.called_in)}, still holds ${weight(c.open)}`}>
                <Name who={c.who} />
                <span className="text-mist tabular-nums">{c.rate}%</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-xs text-mist">Leave them standing</h3>
          <ul className="text-sm">
            {s.leaves.map((c) => (
              <li key={c.who.key} className="flex justify-between gap-2" title={`Holds ${weight(c.open)}, has called in none`}>
                <Name who={c.who} />
                <span className="text-mist tabular-nums">holds {weight(c.open)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function Across({ title, across, line }: { title: string; across: Standings["across_clans"]; line: "clan" | "sect" }) {
  const most = Math.max(0, ...across.pairs.map((p) => p.weight));
  return (
    <Card title={title}>
      <p className="mb-2 text-sm">
        {across.crossing} of {across.of} open boons cross a {line} line, weighing {weight(across.crossing_weight)}.
      </p>
      {across.pairs.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Table
            label={`Between ${line}s`}
            head={
              <tr>
                <th className={cell}>Between</th>
                <th className={num}>Boons</th>
                <th className={num}>Weight</th>
                <th className={cell}>
                  <span className="sr-only">Bar</span>
                </th>
              </tr>
            }
          >
            {across.pairs.map((p) => (
              <tr key={p.label}>
                <td className={cell}>{p.label}</td>
                <td className={num}>{p.count}</td>
                <td className={num}>{weight(p.weight)}</td>
                <td className={`${cell} w-1/3`}>
                  <Bar value={p.weight} most={most} label={`Weight ${weight(p.weight)}`} />
                </td>
              </tr>
            ))}
          </Table>
          <Tallies label={`Most across ${line} lines`} tallies={across.most} />
        </div>
      )}
    </Card>
  );
}

function Mutual({ standings }: { standings: Standings }) {
  return (
    <Card title="Owing each other">
      {standings.mutual.length === 0 ? (
        <Empty>No two characters owe each other.</Empty>
      ) : (
        <Table
          label="Owing each other"
          head={
            <tr>
              <th className={cell}>Owes more</th>
              <th className={cell}>To</th>
              <th className={num}>Owes</th>
              <th className={num}>Back</th>
              <th className={num}>Difference</th>
            </tr>
          }
        >
          {standings.mutual.map((m) => (
            <tr key={`${m.first.key}:${m.second.key}`}>
              <td className={cell}>
                <Name who={m.first} />
              </td>
              <td className={cell}>
                <Name who={m.second} />
              </td>
              <td className={num}>{weight(m.owes)}</td>
              <td className={num}>{weight(m.back)}</td>
              <td className={num}>{weight(m.net)}</td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}
