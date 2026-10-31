import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { StatusRuleOut } from "../../api/types";
import { Explainer } from "../../components/Explainer";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Card, ErrorText, Loading } from "../../components/ui";
import { NO_RULES_YET } from "../character/status";
import { givenByText, STATUS_TYPES } from "./statusRules";

/**
 * Every status of the sects the troupe takes, and the general status, by sect: its
 * type, what it does, and where it comes from (the troupe's titles, social ages,
 * factions and merits). The rule set's; read only.
 */
export function StatusRulesSection({ troupeId }: { troupeId: string }) {
  const rules = useQuery({
    queryKey: ["status-rules", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/status-rules", { params: { path: { troupe_id: troupeId } } })),
  });
  if (rules.isPending) return <Loading />;
  if (rules.error) return <ErrorText error={rules.error} />;
  const { caps, sects } = rules.data;
  const capsPage = pageLabel(caps.page);
  return (
    <div className="flex flex-col gap-6">
      <Explainer id="rules-status" title="How status works">
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
          {STATUS_TYPES.map((t) => (
            <div key={t.type} className="contents">
              <dt>
                <Badge>{t.type.toLowerCase()}</Badge>
              </dt>
              <dd className="mb-1 text-mist sm:mb-0">
                {t.meaning} {pageLabel(t.page)}.
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-sm">
          A character carries into a game the abiding status of {caps.abiding_sources === 1 ? "one source" : `${caps.abiding_sources} sources`} (a title or
          its social age), all its innate and negative status, and up to {caps.fleeting} fleeting status: {caps.lesser_ban} under a lesser status ban,{" "}
          {caps.greater_ban} under a greater.{capsPage && ` ${capsPage}.`}
        </p>
      </Explainer>
      {sects.map((s) => {
        const page = pageLabel(s.page);
        return (
          <Card key={s.sect} title={s.sect === "General" ? "General status" : `${s.sect} status`}>
            <p className="mb-2 text-sm text-mist">
              {s.sect === "General"
                ? "Every sect's: a character Accepted by any sect can hold it."
                : `A character Accepted by the ${s.sect} is ${s.accepted ?? "Accepted"}, and holds its status as well as the general status.`}
              {page && ` ${page}.`}
            </p>
            <ul className="divide-y divide-ash">
              {s.statuses.map((r) => (
                <StatusRow key={r.name} rule={r} />
              ))}
            </ul>
          </Card>
        );
      })}
    </div>
  );
}

function StatusRow({ rule }: { rule: StatusRuleOut }) {
  const page = pageLabel(rule.page);
  const given = givenByText(rule.given_by);
  return (
    <li aria-label={rule.name} className="flex flex-col gap-0.5 py-2.5 text-sm">
      <span className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-parchment">{rule.name}</span>
        <Badge tone={rule.type === "Negative" ? "blood" : "mist"}>{rule.type.toLowerCase()}</Badge>
        {rule.no_rules_yet && <Badge tone="gold">no rules yet</Badge>}
        {page && <span className="text-xs text-mist">{page}</span>}
      </span>
      <span className="flex flex-col text-xs text-mist">
        {rule.no_rules_yet && <span>{NO_RULES_YET}</span>}
        {rule.passive && <span>Held: {rule.passive}</span>}
        {rule.spent && <span>Spent: {rule.spent}</span>}
        {rule.censure && <span>Censure: {rule.censure}</span>}
        {rule.punishment && <span>Punishment: {rule.punishment}</span>}
        {rule.duration && <span>Lasts: {rule.duration}</span>}
        {rule.source && <span>Comes from: {rule.source}</span>}
        {given && <span className="text-parchment/80">{given}</span>}
      </span>
    </li>
  );
}
