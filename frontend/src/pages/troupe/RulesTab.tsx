import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Route, Routes } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CheckOut } from "../../api/types";
import { Badge, Card, ErrorText, Input, Loading, PageTabs, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { AllowancesSection } from "./AllowancesSection";
import { pageText } from "./bookPage";
import { CostsSection } from "./CostsSection";
import { HouseTraitsSection } from "./HouseTraitsSection";
import { LocationRulesSection } from "./LocationRulesSection";
import { QuestSettings } from "./QuestSettings";
import { StartingSection } from "./StartingSection";
import { StatusRulesSection } from "./StatusRulesSection";

type Strength = "refuse" | "complete" | "review" | "note" | "off";

/** What each setting does to a player's sheet, in the order of strictness. */
const STRENGTHS: { value: Strength; label: string; meaning: string; tone: "blood" | "gold" | "mist" }[] = [
  {
    value: "refuse",
    label: "Refuse",
    meaning: "The change is not allowed. The player sees why, and the choice is greyed out in lists.",
    tone: "blood",
  },
  {
    value: "complete",
    label: "Needed to finish",
    meaning:
      "Allowed while the character is being built, but creation cannot be finished until the rule is met. Afterwards it refuses, like Refuse.",
    tone: "blood",
  },
  {
    value: "review",
    label: "Allow, for our review",
    meaning:
      "Once the character has this troupe as home, the change goes through but waits on the Approvals tab. Declining takes it back and refunds the XP. Before then it is allowed, as accepting the character reviews the whole sheet.",
    tone: "gold",
  },
  {
    value: "note",
    label: "Only note it",
    meaning: "Allowed. The sheet lists it under “Against the rules” so storytellers can see it.",
    tone: "mist",
  },
  { value: "off", label: "Off", meaning: "The rule does not apply in this troupe at all.", tone: "mist" },
];
const strength = (value: string) => STRENGTHS.find((s) => s.value === value);

/** Headings for what a rule is about, by trait category. */
const ABOUT: Record<string, string> = {
  merits: "Merits",
  flaws: "Flaws",
  disciplines: "Disciplines",
  techniques: "Techniques",
  elder_disciplines: "Elder powers",
  rituals: "Rituals",
  skills: "Skills",
  backgrounds: "Backgrounds",
  clan: "Clan",
  paths: "Morality",
  focus_socials: "Focuses",
  extra_in_clan_disciplines: "Extra in-clan disciplines",
  lore_specializations: "Specialisations",
  linguistics_specializations: "Specialisations",
};

/**
 * The troupe's house rules, part by part: how it plays the rule set's checks,
 * what traits cost here, what new characters start with, how many downtime
 * actions characters get, and the troupe's own merits and flaws; and the status
 * of each sect it takes, with where each comes from here.
 */
export function RulesTab({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const base = `/troupes/${troupeId}/rules`;
  return (
    <>
      <PageTabs
        label="House rules"
        tabs={[
          { to: base, label: "Checks", end: true },
          { to: `${base}/costs`, label: "Costs" },
          { to: `${base}/starting`, label: "Starting points" },
          { to: `${base}/actions`, label: "Downtime actions" },
          { to: `${base}/house-traits`, label: "House merits and flaws" },
          { to: `${base}/status`, label: "Status" },
          { to: `${base}/locations`, label: "Locations" },
          { to: `${base}/quests`, label: "Quests" },
        ]}
      />
      <Routes>
        <Route index element={<ChecksSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="costs" element={<CostsSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="starting" element={<StartingSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="actions" element={<AllowancesSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="house-traits" element={<HouseTraitsSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="status" element={<StatusRulesSection troupeId={troupeId} />} />
        <Route path="locations" element={<LocationRulesSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="quests" element={<QuestSettings troupeId={troupeId} canEdit={canEdit} />} />
      </Routes>
    </>
  );
}

/**
 * The rule set's checks and how this troupe plays them. Storytellers can make a
 * check stricter or looser, review it themselves, or switch it off; it applies
 * to characters whose home troupe this is.
 */
function ChecksSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [query, setQuery] = useState("");
  const [onlyChanged, setOnlyChanged] = useState(false);
  const checks = useQuery({
    queryKey: ["checks", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/checks", { params: { path: { troupe_id: troupeId } } })),
  });
  const change = useAction((body: { key: string; strength: Strength | null }) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/checks/{key}", {
        params: { path: { troupe_id: troupeId, key: body.key } },
        body: { strength: body.strength },
      }),
    ),
  );
  if (checks.isPending) return <Loading />;
  if (checks.error) return <ErrorText error={checks.error} />;

  const q = query.trim().toLowerCase();
  const shown = checks.data.filter(
    (c) => (!onlyChanged || c.house) && (!q || `${c.about} ${c.message}`.toLowerCase().includes(q)),
  );
  const groups = new Map<string, CheckOut[]>();
  for (const c of shown) {
    const heading = ABOUT[c.category] ?? "Other";
    groups.set(heading, [...(groups.get(heading) ?? []), c]);
  }
  const changed = checks.data.filter((c) => c.house).length;

  return (
    <div className="flex flex-col gap-6">
      <Card title="How rules work">
        <p className="mb-3 text-sm">
          Each rule below comes from the rule set and says what a sheet may hold, with the book page, and how
          this troupe plays it.{" "}
          {canEdit
            ? "Choose another setting to play it differently here; “As written” goes back to the rule set's."
            : "Storytellers can play a rule differently here."}{" "}
          A setting here applies to characters whose home troupe this is.
        </p>
        <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
          {STRENGTHS.map((s) => (
            <div key={s.value} className="contents">
              <dt>
                <Badge tone={s.tone}>{s.label}</Badge>
              </dt>
              <dd className="mb-1 text-mist sm:mb-0">{s.meaning}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card title="Rules">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Input
            aria-label="Search rules"
            placeholder={`Search ${checks.data.length} rules…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-48 flex-1"
          />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyChanged} onChange={(e) => setOnlyChanged(e.target.checked)} />
            Only those played differently ({changed})
          </label>
        </div>
        {shown.length === 0 && <p className="text-sm text-mist">No rules match.</p>}
        <div className="flex flex-col gap-5">
          {[...groups].map(([heading, rules]) => (
            <section key={heading}>
              <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{heading}</h3>
              <ul className="divide-y divide-ash">
                {rules.map((c) => (
                  <RuleRow key={c.key} rule={c} canEdit={canEdit} onChange={(value) => change.mutate({ key: c.key, strength: value })} />
                ))}
              </ul>
            </section>
          ))}
        </div>
        <ErrorText error={change.error} />
      </Card>
    </div>
  );
}

function RuleRow({ rule, canEdit, onChange }: { rule: CheckOut; canEdit: boolean; onChange: (value: Strength | null) => void }) {
  const played = strength(rule.house ?? rule.strength);
  return (
    <li className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:gap-4">
      <span className="min-w-0 flex-1 text-sm">
        <span className="text-parchment">{rule.message || rule.about}</span>
        {rule.page && <span className="text-mist"> {pageText(rule.page)}</span>}
        {rule.house && <span className="ml-2 text-xs text-gold">(changed here)</span>}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {played && !canEdit && <Badge tone={played.tone}>{played.label}</Badge>}
        {canEdit && (
          <Select
            aria-label={`Setting for: ${rule.message || rule.about}`}
            value={rule.house ?? ""}
            onChange={(e) => onChange((e.target.value || null) as Strength | null)}
            className={`min-h-8 w-56 py-1 text-sm ${rule.house ? "border-gold/60 text-gold" : ""}`}
          >
            <option value="">As written ({strength(rule.strength)?.label ?? rule.strength})</option>
            {STRENGTHS.filter((s) => s.value !== rule.strength).map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        )}
      </span>
    </li>
  );
}
