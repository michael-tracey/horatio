import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Route, Routes } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CheckOut } from "../../api/types";
import { EmptyState } from "../../components/EmptyState";
import { Explainer } from "../../components/Explainer";
import { useToast } from "../../components/Toast";
import { Badge, Button, ErrorText, Input, Loading, PageTabs, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { AllowancesSection } from "./AllowancesSection";
import { BackstorySettings } from "./BackstorySettings";
import { pageText } from "./bookPage";
import { CostsSection } from "./CostsSection";
import { FreeChangesSettings } from "./FreeChangesSettings";
import { HouseTraitsSection } from "./HouseTraitsSection";
import { LocationRulesSection } from "./LocationRulesSection";
import { QuestSettings } from "./QuestSettings";
import { StartingSection } from "./StartingSection";

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

/**
 * The troupe's house rules, part by part: how it plays the rule set's checks,
 * what traits cost here, what new characters start with, how many downtime
 * actions characters get, and the troupe's own merits and flaws. The status of
 * each sect is a reference of its own, on the Troupe group's Status tab.
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
          { to: `${base}/locations`, label: "Locations" },
          { to: `${base}/quests`, label: "Quests" },
          { to: `${base}/backstories`, label: "Backstories" },
          { to: `${base}/free-changes`, label: "Free changes" },
        ]}
      />
      <Routes>
        <Route index element={<ChecksSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="costs" element={<CostsSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="starting" element={<StartingSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="actions" element={<AllowancesSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="house-traits" element={<HouseTraitsSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="locations" element={<LocationRulesSection troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="quests" element={<QuestSettings troupeId={troupeId} canEdit={canEdit} />} />
        <Route path="backstories" element={<BackstorySettings troupeId={troupeId} />} />
        <Route path="free-changes" element={<FreeChangesSettings troupeId={troupeId} canEdit={canEdit} />} />
      </Routes>
    </>
  );
}

/**
 * The rule set's checks and how this troupe plays them. Storytellers can make a
 * check stricter or looser, review it themselves, or switch it off; it applies
 * to characters whose home troupe this is. There are hundreds, so they come in
 * groups by kind, folded, and the page opens on the troupe's house rules alone; a
 * search looks through them all. A change saves at once, like the other settings
 * in Customise, and says so with a toast that can undo it.
 */
function ChecksSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"house" | "all">("house");
  // Checks changed on this visit stay in the house rules view, even once back as written.
  const [touched, setTouched] = useState<Set<string>>(new Set());
  // Groups opened or closed by hand, until the search or the view changes.
  const [folded, setFolded] = useState<Map<string, boolean>>(new Map());
  const toast = useToast();
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
  const changed = checks.data.filter((c) => c.house).length;
  const shown = checks.data.filter((c) =>
    q ? `${c.group} ${c.about} ${c.message}`.toLowerCase().includes(q) : view === "all" || c.house || touched.has(c.key),
  );
  const groups = groupChecks(shown);
  const totals = groupChecks(checks.data);
  // A search or the house rules view shows only a few, so their groups open; all checks start folded.
  const opens = !!q || view === "house";
  const choose = (next: "house" | "all") => {
    setView(next);
    setFolded(new Map());
  };

  const play = (rule: CheckOut, strength: Strength | null) => {
    const before = rule.house as Strength | null;
    const what = rule.about === "any" ? "the check" : rule.about;
    setTouched((t) => new Set(t).add(rule.key));
    change.mutate(
      { key: rule.key, strength },
      {
        onSuccess: () =>
          toast({
            message: `Saved: ${what} ${strength ? `is now ${strengthLabel(strength)}` : "is back as written"}`,
            action: { label: "Undo", onClick: () => change.mutate({ key: rule.key, strength: before }) },
          }),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <Explainer id="rules-checks" title="How checks work">
        <p className="mb-3 text-sm">
          Each check comes from the rule set and says what a sheet may hold, with the book page, and how this troupe
          plays it.{" "}
          {canEdit
            ? "Choose another setting to play it differently here; “As written” goes back to the rule set's. A change saves at once."
            : "Storytellers can play a check differently here."}{" "}
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
      </Explainer>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            type="search"
            aria-label="Search checks"
            placeholder={`Search all ${checks.data.length} checks…`}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setFolded(new Map());
            }}
            className="min-w-48 flex-1"
          />
          <div role="group" aria-label="Which checks" className="inline-flex gap-0.5 rounded-md border border-ash bg-night p-0.5">
            {(
              [
                ["house", `House rules (${changed})`],
                ["all", `All checks (${checks.data.length})`],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={!q && view === value}
                disabled={!!q}
                onClick={() => choose(value)}
                className={`min-h-8 rounded px-2.5 py-1 text-xs whitespace-nowrap disabled:opacity-60 ${
                  !q && view === value ? "bg-ash text-gold" : "text-mist hover:text-parchment"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {q && <p className="text-xs text-mist">Searching all {checks.data.length} checks.</p>}
      </div>

      {shown.length === 0 &&
        (q ? (
          <EmptyState title="No checks match." />
        ) : (
          <EmptyState
            title="No house rules yet."
            action={
              <Button variant="secondary" onClick={() => choose("all")}>
                Show all checks
              </Button>
            }
          >
            Every check plays as the book has it. Search, or show all checks, to play one differently.
          </EmptyState>
        ))}
      <div role="group" aria-label="Checks by kind" className="flex flex-col gap-3">
        {[...groups].map(([group, rules]) => {
          const open = folded.get(group) ?? opens;
          const all = totals.get(group) ?? rules;
          const house = all.filter((c) => c.house).length;
          return (
            <details
              key={group}
              open={open}
              onToggle={(e) => {
                const now = e.currentTarget.open;
                if (now !== open) setFolded((f) => new Map(f).set(group, now));
              }}
              className="group rounded-lg border border-ash bg-dusk"
            >
              <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 py-3 sm:px-5 [&::-webkit-details-marker]:hidden">
                <h2 className="text-base text-gold">{group}</h2>
                <span className="flex items-center gap-2 text-sm text-mist">
                  {house > 0 && <Badge tone="gold">{house === 1 ? "1 house rule" : `${house} house rules`}</Badge>}
                  {rules.length < all.length ? `${rules.length} of ${all.length}` : all.length} {all.length === 1 ? "check" : "checks"}
                  <span aria-hidden className="transition-transform group-open:rotate-90">
                    ›
                  </span>
                </span>
              </summary>
              {/* Rows only while open: a group can hold hundreds, each with its select. */}
              {open && (
                <ul className="divide-y divide-ash border-t border-ash px-4 sm:px-5">
                  {rules.map((c) => (
                    <RuleRow key={c.key} rule={c} canEdit={canEdit} onChange={(value) => play(c, value)} />
                  ))}
                </ul>
              )}
            </details>
          );
        })}
      </div>
      <ErrorText error={change.error} />
    </div>
  );
}

/** Checks by their group, in the order the rules list the groups. */
function groupChecks(checks: CheckOut[]): Map<string, CheckOut[]> {
  const groups = new Map<string, CheckOut[]>();
  for (const c of checks) {
    const list = groups.get(c.group);
    if (list) list.push(c);
    else groups.set(c.group, [c]);
  }
  return groups;
}

const strengthLabel = (value: string) => strength(value)?.label ?? value;

function RuleRow({ rule, canEdit, onChange }: { rule: CheckOut; canEdit: boolean; onChange: (value: Strength | null) => void }) {
  const played = strength(rule.house ?? rule.strength);
  return (
    <li className="flex flex-col gap-2 py-2.5 sm:flex-row sm:items-center sm:gap-4">
      <span className="min-w-0 flex-1 text-sm">
        <span className="text-parchment">{rule.message || rule.about}</span>
        {rule.page && <span className="text-mist"> {pageText(rule.page)}</span>}
        {rule.house && (
          <span className="ml-2">
            <Badge tone="gold">House rule</Badge>
          </span>
        )}
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
