import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SetupOut, TroupeOut } from "../../api/types";
import { Badge, Card, ErrorText, Loading } from "../../components/ui";
import { sectsText, useSplatsText } from "./SettingsTab";

/**
 * The first tab of Customise (issue #377): the few things a new lead sets up
 * first, each done or not with a link to where it is done, then the troupe's house
 * settings at a glance, each with the tab that changes it. Everything else in
 * Customise can stay as the book has it.
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
      <AtAGlance troupe={troupe} setup={setup.data} canEdit={canEdit} />
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

const WHO: Record<string, string> = {
  players: "players keep their own",
  staff: "staff only",
};
const CONNECTOR_STATE: Record<SetupOut["connectors"][number]["state"], string> = {
  on: "on",
  test: "on, in test mode",
  off: "off",
  unavailable: "not set up on this server",
};

/** The troupe's settings in a line each, with where each is changed. */
function AtAGlance({ troupe, setup: s, canEdit }: { troupe: TroupeOut; setup: SetupOut; canEdit: boolean }) {
  const base = `/troupes/${troupe.id}`;
  // Assistant storytellers read the settings; storytellers change them.
  const action = canEdit ? "Change" : "See";
  const { text: splats } = useSplatsText(troupe);
  const asBook = (n: number, what: (n: number) => string) => (n > 0 ? what(n) : "As the book has it");
  return (
    <Card title="House settings at a glance">
      <dl className="flex flex-col divide-y divide-ash text-sm">
        <SettingRow action={action} label="Who may join" to={`${base}/settings`}>
          {splats} player characters. {sectsText(troupe.allowed_sects)}
        </SettingRow>
        <SettingRow action={action} label="XP" to={`${base}/settings`}>
          {troupe.session_xp} a game and {troupe.downtime_xp} a downtime. New characters start at {troupe.xp_floor} XP; the ceiling is{" "}
          {troupe.xp_ceiling}.
        </SettingRow>
        <SettingRow action={action} label="Status and titles" to={`${base}/settings`}>
          Status on sheets: {WHO[troupe.status_by] ?? troupe.status_by}. Titles: {WHO[troupe.titles_by] ?? troupe.titles_by}.
        </SettingRow>
        <SettingRow action={action} label="Checks" to={`${base}/rules`}>
          {s.checks} of {s.checks_total} played differently
        </SettingRow>
        <SettingRow action={action} label="Costs" to={`${base}/rules/costs`}>
          {asBook(s.costs, (n) => (n === 1 ? "1 house price" : `${n} house prices`))}
        </SettingRow>
        <SettingRow action={action} label="Starting points" to={`${base}/rules/starting`}>
          {asBook(s.starting, houseRules)}
        </SettingRow>
        <SettingRow action={action} label="Downtime actions" to={`${base}/rules/actions`}>
          {asBook(s.actions, houseRules)}
        </SettingRow>
        <SettingRow action={action} label="House merits and flaws" to={`${base}/rules/house-traits`}>
          {s.house_traits > 0 ? `${s.house_traits} of the troupe's own` : "None"}
        </SettingRow>
        <SettingRow action={action} label="Quests" to={`${base}/rules/quests`}>
          {troupe.quests_enabled
            ? `On: ${troupe.quest_requests_per_cycle} ${troupe.quest_requests_per_cycle === 1 ? "request" : "requests"} a character each cycle`
            : "Off"}
        </SettingRow>
        <SettingRow action={action} label="Connectors" to={`${base}/connectors`}>
          {s.connectors.length === 0
            ? "Results reach players in Horatio."
            : `In Horatio, always. ${s.connectors.map((c) => `${c.name}: ${CONNECTOR_STATE[c.state]}`).join(". ")}.`}
        </SettingRow>
      </dl>
    </Card>
  );
}

function SettingRow({ label, to, action, children }: { label: string; to: string; action: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="text-mist sm:w-44 sm:shrink-0">{label}</dt>
      <dd className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3">
        <span>{children}</span>
        <Link to={to} className="text-xs text-mist underline hover:text-parchment" aria-label={`${action}: ${label}`}>
          {action}
        </Link>
      </dd>
    </div>
  );
}
