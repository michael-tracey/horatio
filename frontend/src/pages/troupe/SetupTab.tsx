import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SetupOut, TroupeOut } from "../../api/types";
import { Badge, Card, ErrorText, Loading } from "../../components/ui";
import { features } from "./features";

/**
 * The first tab of Customise (issue #377): the few things a new lead sets up
 * first, each done or not with a link to where it is done; then the troupe's
 * features, on or off, and the parts of its rules it plays differently from the
 * book (#786). Nothing is changed here: each line points to where it is.
 */
export function SetupTab({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const setup = useQuery({
    queryKey: ["setup", troupe.id],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/setup", {
          params: { path: { troupe_id: troupe.id } },
        }),
      ),
  });
  if (setup.isPending) return <Loading />;
  if (setup.error) return <ErrorText error={setup.error} />;
  return (
    <div className="flex flex-col gap-6">
      <Checklist troupe={troupe} setup={setup.data} />
      <Features troupe={troupe} canEdit={canEdit} />
      <HouseRules troupe={troupe} setup={setup.data} canEdit={canEdit} />
    </div>
  );
}

/** How many house rules it has in all, across every part of Rules. */
function houseRuleCount(s: SetupOut): number {
  return s.checks + s.costs + s.starting + s.actions + s.house_traits + s.other;
}

/** "1 house rule", "3 house rules". */
const houseRules = (n: number) => (n === 1 ? "1 house rule" : `${n} house rules`);

function Checklist({ troupe, setup: s }: { troupe: TroupeOut; setup: SetupOut }) {
  const base = `/troupes/${troupe.id}`;
  const rules = houseRuleCount(s);
  const steps: { label: string; done: boolean; text: string; to: string }[] = [
    {
      label: "Name and profile",
      done: s.described && s.profile,
      text:
        s.described && s.profile
          ? "Described, with a profile for players choosing a troupe."
          : s.described
            ? "Add a portrait, links, and when and where you play."
            : "Describe the troupe, then add a portrait and when and where you play.",
      to: `${base}/profile`,
    },
    {
      label: "House rules",
      done: rules > 0,
      text:
        rules > 0
          ? `${houseRules(rules)}. Anything else plays as the book has it.`
          : "None yet: everything plays as the book has it. Change what you play differently.",
      to: `${base}/rules`,
    },
    {
      label: "Staff",
      done: s.staff > 0,
      text:
        s.staff > 0
          ? `${s.staff} besides the lead storyteller.`
          : "Only the lead storyteller so far. Add storytellers, assistants and narrators to share the work.",
      to: `${base}/staff`,
    },
    {
      label: "First cycle",
      done: s.cycles > 0,
      text: s.cycles > 0 ? "Downtimes have begun." : "Open the first downtime cycle once players have characters.",
      to: `${base}/downtimes`,
    },
  ];
  const done = steps.filter((step) => step.done).length;
  return (
    <Card title="Setting up" actions={<Badge tone={done === steps.length ? "gold" : "mist"}>{`${done} of ${steps.length} done`}</Badge>}>
      <ol className="divide-y divide-ash" aria-label="Setting up">
        {steps.map((step) => (
          <li key={step.label}>
            <Link to={step.to} className="flex items-start gap-3 py-2.5 text-sm hover:text-gold">
              <span
                aria-hidden
                className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-xs ${
                  step.done ? "border-gold/60 bg-gold/15 text-gold" : "border-line text-transparent"
                }`}
              >
                ✓
              </span>
              <span className="min-w-0 flex-1">
                <span className="text-parchment">{step.label}</span>
                <span className="sr-only">{step.done ? ": done." : ": to do."}</span>
                <span className="block text-mist">{step.text}</span>
              </span>
              <span aria-hidden className="text-mist">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </Card>
  );
}

/** The troupe's features, each on or off and linked to its tab; switched in Troupe settings. */
function Features({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const base = `/troupes/${troupe.id}`;
  const all = features(troupe);
  const on = all.filter((f) => f.on).length;
  return (
    <Card
      title="Features"
      actions={
        <Link to={`${base}/settings`} className="text-xs text-mist underline hover:text-parchment">
          {canEdit ? "Switch them in Troupe settings" : "See them in Troupe settings"}
        </Link>
      }
    >
      <p className="mb-2 text-sm text-mist">{`${on} of ${all.length} on.`}</p>
      <ul aria-label="Features at a glance" className="flex flex-col divide-y divide-ash text-sm">
        {all.map((f) => (
          <li key={f.key} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
            {f.tab ? (
              <Link to={`${base}/${f.tab.to}`} className="text-parchment underline decoration-ash hover:text-gold">
                {f.name}
              </Link>
            ) : (
              <span className="text-parchment">{f.name}</span>
            )}
            <Badge tone={f.on ? "gold" : "mist"}>{f.state}</Badge>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-mist">
        Who may join, XP, status and titles and the setting are on{" "}
        <Link to={`${base}/settings`} className="underline hover:text-parchment">
          Troupe settings
        </Link>{" "}
        too.
      </p>
    </Card>
  );
}

export type RuleArea = { label: string; text: string; to: string };

/**
 * The parts of the troupe's rules it plays differently from the book, a line each
 * with where it is: none when everything plays as the book has it.
 */
export function differentAreas(s: SetupOut, base: string): RuleArea[] {
  const areas: (RuleArea | false)[] = [
    s.checks > 0 && { label: "Checks", text: `${s.checks} of ${s.checks_total} played differently`, to: `${base}/rules` },
    s.costs > 0 && { label: "Costs", text: s.costs === 1 ? "1 house price" : `${s.costs} house prices`, to: `${base}/rules/costs` },
    s.starting > 0 && { label: "Starting points", text: houseRules(s.starting), to: `${base}/rules/starting` },
    s.actions > 0 && { label: "Downtime actions", text: houseRules(s.actions), to: `${base}/rules/actions` },
    s.house_traits > 0 && { label: "House merits and flaws", text: `${s.house_traits} of the troupe's own`, to: `${base}/rules/house-traits` },
    s.other > 0 && { label: "Other house rules", text: s.other === 1 ? "1 setting unlike the book" : `${s.other} settings unlike the book`, to: `${base}/house-rules` },
  ];
  return areas.filter((a): a is RuleArea => !!a);
}

/** Where the troupe plays differently from the book, each linked into its rules. */
function HouseRules({ troupe, setup, canEdit }: { troupe: TroupeOut; setup: SetupOut; canEdit: boolean }) {
  const base = `/troupes/${troupe.id}`;
  const areas = differentAreas(setup, base);
  return (
    <Card
      title="House rules"
      actions={
        <Link to={`${base}/house-rules`} className="text-xs text-mist underline hover:text-parchment">
          Read them as players do
        </Link>
      }
    >
      {areas.length === 0 ? (
        <p className="text-sm text-mist">
          Everything plays as the book has it.{" "}
          <Link to={`${base}/rules`} className="underline hover:text-parchment">
            {canEdit ? "Change what you play differently" : "See the rules"}
          </Link>
          .
        </p>
      ) : (
        <ul aria-label="Played differently" className="flex flex-col divide-y divide-ash text-sm">
          {areas.map((a) => (
            <li key={a.label}>
              <Link to={a.to} className="flex flex-wrap items-baseline justify-between gap-x-3 py-2 hover:text-gold">
                <span className="text-parchment">{a.label}</span>
                <span className="text-mist">{a.text}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
