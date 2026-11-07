import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { AimedOut, CycleOut, TargetOut } from "../../api/types";
import { Badge, Empty, ErrorText, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { COUNTER_NAMES, type Counter } from "../character/aim";
import { STATUS_NAMES } from "./responsesList";

/**
 * The cycle's actions aimed at characters, by the character they are aimed at
 * (#507): who, which question and the answer, each linking to its response. Where
 * staff resolve spying, cancelling and watching. Players never see it.
 */
export function AimedTab({ cycle }: { cycle: CycleOut }) {
  const aimed = useQuery({
    queryKey: ["aimed", cycle.id],
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/aimed", { params: { path: { cycle_id: cycle.id } } })),
  });
  if (aimed.isPending) return <Loading />;
  if (aimed.error) return <ErrorText error={aimed.error} />;
  if (aimed.data.length === 0) return <Empty>No submitted action is aimed at anyone yet.</Empty>;
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-mist">Only storytellers and assistant storytellers see this. No player learns who aimed an action at them.</p>
      {aimed.data.map((target) => (
        <section key={target.character_id} aria-label={`Aimed at ${target.character_name}`} className="flex flex-col gap-2">
          <h2 className="border-b border-ash pb-1 font-medium text-gold">
            {target.character_name}{" "}
            <span className="text-xs font-normal text-mist">
              {target.actions.length} {target.actions.length === 1 ? "action" : "actions"} aimed at them
            </span>
          </h2>
          <ul className="flex flex-col gap-2">
            {target.actions.map((a) => (
              <AimedAction key={a.response_id} cycleId={cycle.id} target={target} action={a} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function AimedAction({ cycleId, target, action: a }: { cycleId: string; target: TargetOut; action: AimedOut }) {
  const pair = useAction((responseId: string) =>
    unwrap(api.PUT("/api/responses/{response_id}/pairing", { params: { path: { response_id: a.response_id } }, body: { response_id: responseId || null } })),
  );
  const counter = a.counter ? COUNTER_NAMES[a.counter as Counter] : null;
  return (
    <li className="flex flex-col gap-1 rounded-md border border-ash bg-night/50 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <strong className="text-parchment">{a.character_name}</strong> · {a.question}
          {counter && <Badge tone="gold" className="ml-2">{counter}</Badge>}
        </span>
        <Link to={`/cycles/${cycleId}/responses#response-${a.response_id}`} className="text-gold underline hover:text-parchment">
          Response ({STATUS_NAMES[a.status as keyof typeof STATUS_NAMES]?.toLowerCase() ?? a.status})
        </Link>
      </div>
      <p className="whitespace-pre-line">{a.answer}</p>
      {a.also.length > 0 && <p className="text-mist">Also aimed at {a.also.join(", ")}.</p>}
      {a.located && (
        <p className="text-mist">
          {a.not_against ? "Not against them, so it costs 1 action." : `${target.character_name}'s Haven has Location: it costs 2 actions.`}
        </p>
      )}
      {counter && (
        <label className="flex flex-col gap-1 text-mist">
          Which of {target.character_name}'s actions it {a.counter === "cancel" ? "cancels" : "watches"}
          <Select value={a.paired?.response_id ?? ""} onChange={(e) => pair.mutate(e.target.value)} disabled={pair.isPending}>
            <option value="">Not paired yet</option>
            {target.own.map((o) => (
              <option key={o.response_id} value={o.response_id}>
                {o.question}: {o.answer.length > 60 ? `${o.answer.slice(0, 60)}…` : o.answer}
              </option>
            ))}
          </Select>
        </label>
      )}
      {a.paired && (
        <p className="rounded-md border border-gold/60 p-2">
          <span className="text-mist">Paired with {a.paired.question}: </span>
          {a.paired.answer}
        </p>
      )}
      <ErrorText error={pair.error} />
    </li>
  );
}
