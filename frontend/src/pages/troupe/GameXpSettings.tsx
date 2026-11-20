import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { GameXpSettings } from "../../api/types";
import { RadioList } from "../../components/RadioList";
import { Checkbox } from "../../components/Checkbox";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { Button, Card, ErrorText, Input } from "../../components/ui";
import { addBand, adjustmentText, bandLabel, BOOK_MONTHLY, capText, DEFAULTS, fromRows, PRESETS, removeBand, toRows, type BandRow } from "./gameXp";
import { SectionLabel } from "../../components/Headings";
import { SETTINGS } from "./settingsIndex";

/** Said wherever absentee games are: Horatio doesn't take payments. */
export const PAYMENTS_NOTE = "Payments aren't tracked in Horatio: marking a character absentee is the record, paid or not.";

export function useGameXp(troupeId: string) {
  return useQuery({
    queryKey: ["game-xp", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/game-xp", { params: { path: { troupe_id: troupeId } } })),
  });
}

/** The chart as a table: each earned-XP band, and its XP for a game attended and (while the troupe records them) an absentee game. */
export function GameXpChart({ settings, label = "Game XP chart" }: { settings: GameXpSettings; label?: string }) {
  return (
    <table aria-label={label} className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-mist">
          <th className="py-1 pr-3 font-normal">Earned XP</th>
          <th className="py-1 pr-3 font-normal">Attended</th>
          {settings.absentee && <th className="py-1 font-normal">Absentee</th>}
        </tr>
      </thead>
      <tbody className="divide-y divide-ash">
        {settings.bands.map((b, i) => (
          <tr key={i}>
            <td className="py-1.5 pr-3">{bandLabel(settings.bands, i)}</td>
            <td className="py-1.5 pr-3 text-gold">{b.attended} XP</td>
            {settings.absentee && <td className="py-1.5 text-gold">{b.absentee} XP</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The troupe's game XP in a few lines, for anyone to read. */
function Summary({ settings, sessionXp }: { settings: GameXpSettings; sessionXp: number }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      {settings.bands.length ? (
        <GameXpChart settings={settings} />
      ) : (
        <p>Flat: everyone there gets the same XP, {sessionXp} unless changed when awarding.</p>
      )}
      {settings.adjustments.length > 0 && (
        <p>
          <span className="text-mist">Adjustments, ticked when awarding: </span>
          {settings.adjustments.map(adjustmentText).join("; ")}
        </p>
      )}
      <p>
        <span className="text-mist">Monthly XP: </span>
        {capText(settings)}
      </p>
      <p>
        <span className="text-mist">Absentee games: </span>
        {settings.absentee
          ? `Recorded by ${settings.absentee_by_players ? "staff or the player" : "staff"}.${
              settings.absentee_downtime ? ` A downtime needs a game attended in the ${settings.absentee_lookback_days} days before its cycle closes.` : ""
            }`
          : "Not recorded."}
      </p>
      {settings.absentee && <p className="text-xs text-mist">{PAYMENTS_NOTE}</p>}
    </div>
  );
}

const CAPS: { value: GameXpSettings["cap"]; label: string; meaning: string }[] = [
  { value: "warn", label: "Warn", meaning: "Staff are warned when an award takes a character past the figure, and can still give it." },
  { value: "cap", label: "Cap", meaning: "Awards stop at the figure: the excess isn't given. A figure set by hand isn't held back." },
  { value: "off", label: "Off", meaning: "No monthly figure." },
];

type AdjustmentRow = { key: string; name: string; amount: string; perMonth: string };

/**
 * Game XP (issue #438): a chart of XP by earned-XP band for a game attended and an
 * absentee game, adjustments staff tick when awarding, the monthly cap, and absentee
 * games. With nothing set it is the book's way: everyone there gets the same XP,
 * warned past 10 a month. Its storytellers change it, its fields always open and saved
 * with one button; players see it on the House rules tab.
 */
export function GameXpCard({ troupeId, canEdit, sessionXp }: { troupeId: string; canEdit: boolean; sessionXp: number }) {
  const found = useGameXp(troupeId);
  if (found.isPending) return null;
  if (found.error) return <ErrorText error={found.error} />;
  return (
    <SettingCard
      setting={SETTINGS.gameXp}
      className="md:col-span-2"
      readOnly={!canEdit}
    >
      {canEdit ? <Editor troupeId={troupeId} settings={found.data} /> : <Summary settings={found.data} sessionXp={sessionXp} />}
    </SettingCard>
  );
}

/** The chart as the form holds it, typed figures as text. */
type Draft = {
  rows: BandRow[];
  adjustments: AdjustmentRow[];
  cap: GameXpSettings["cap"];
  monthly: string;
  absentee: boolean;
  byPlayers: boolean;
  downtime: boolean;
  lookback: string;
};

function draftOf(settings: GameXpSettings): Draft {
  return {
    rows: toRows(settings.bands),
    adjustments: settings.adjustments.map((a) => ({ key: a.key, name: a.name, amount: String(a.amount), perMonth: a.per_month == null ? "" : String(a.per_month) })),
    cap: settings.cap,
    monthly: settings.monthly_xp == null ? "" : String(settings.monthly_xp),
    absentee: settings.absentee,
    byPlayers: settings.absentee_by_players,
    downtime: settings.absentee_downtime,
    lookback: String(settings.absentee_lookback_days),
  };
}

/** The settings a draft makes; a problem with it is thrown, for the form to show. */
function bodyOf(d: Draft): GameXpSettings {
  const chart = fromRows(d.rows);
  if (chart.error !== null) throw new Error(chart.error);
  const bad = d.adjustments.find((a) => !a.name.trim() || !/^-?\d+$/.test(a.amount.trim()) || Number(a.amount) === 0 || (a.perMonth.trim() !== "" && !/^\d+$/.test(a.perMonth.trim())));
  if (bad) throw new Error(`Give ${bad.name.trim() || "each adjustment"} a name, an amount more or less than 0, and any monthly limit as a whole number.`);
  return {
    ...DEFAULTS,
    bands: chart.bands,
    adjustments: d.adjustments.map((a) => ({ key: a.key, name: a.name.trim(), amount: Number(a.amount), per_month: a.perMonth.trim() ? Number(a.perMonth) : null })),
    cap: d.cap,
    monthly_xp: d.monthly.trim() ? Number(d.monthly) : null,
    absentee: d.absentee,
    absentee_by_players: d.absentee && d.byPlayers,
    absentee_downtime: d.absentee && d.downtime,
    absentee_lookback_days: Number(d.lookback) || 60,
  };
}

function Editor({ troupeId, settings }: { troupeId: string; settings: GameXpSettings }) {
  const form = useSettingForm(
    draftOf(settings),
    (d) => unwrap(api.PUT("/api/troupes/{troupe_id}/game-xp", { params: { path: { troupe_id: troupeId } }, body: bodyOf(d) })),
    {
      first: [
        ["game-xp", troupeId],
        ["house-rules", troupeId],
      ],
    },
  );
  const { rows, adjustments, cap, monthly, absentee, byPlayers, downtime, lookback } = form.value;
  const setRows = (next: BandRow[]) => form.set({ rows: next });
  const setAdjustments = (next: AdjustmentRow[]) => form.set({ adjustments: next });
  const changeRow = (i: number, change: Partial<BandRow>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const changeAdjustment = (i: number, change: Partial<AdjustmentRow>) => setAdjustments(adjustments.map((a, j) => (j === i ? { ...a, ...change } : a)));

  return (
    <SettingForm form={form} className="gap-5">
      <section aria-labelledby="xp-bands" className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SectionLabel id="xp-bands">By earned XP</SectionLabel>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Start from a preset">
            <span className="text-xs text-mist">Start from:</span>
            {PRESETS.map((p) => (
              <Button key={p.name} type="button" variant="secondary" className="min-h-8 px-3" onClick={() => setRows(toRows(p.bands))}>
                {p.name}
              </Button>
            ))}
          </div>
        </div>
        {rows.length === 0 ? (
          <p className="text-mist">Flat: everyone there gets the same XP, the session XP unless changed when awarding. Add a band to taper it by earned XP.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {rows.map((r, i) => {
              const last = i === rows.length - 1;
              const low = i === 0 ? 0 : (Number(rows[i - 1]?.upTo) || 0) + 1;
              return (
                <li key={i} className="flex flex-wrap items-center gap-2">
                  <span className="w-12 text-mist">{low}</span>
                  {last ? (
                    <span className="w-24 text-mist">and above</span>
                  ) : (
                    <label className="flex items-center gap-1">
                      <span className="text-mist">to</span>
                      <Input
                        type="number"
                        min={0}
                        aria-label={`Band ${i + 1}: earned XP up to`}
                        value={r.upTo}
                        onChange={(e) => changeRow(i, { upTo: e.target.value })}
                        className="w-20"
                      />
                    </label>
                  )}
                  <label className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      aria-label={`Band ${i + 1}: XP attended`}
                      value={r.attended}
                      onChange={(e) => changeRow(i, { attended: e.target.value })}
                      className="w-16"
                    />
                    <span className="text-mist">attended</span>
                  </label>
                  <label className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      aria-label={`Band ${i + 1}: XP absentee`}
                      value={r.absentee}
                      onChange={(e) => changeRow(i, { absentee: e.target.value })}
                      className="w-16"
                    />
                    <span className="text-mist">absentee</span>
                  </label>
                  <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove band ${i + 1}`} onClick={() => setRows(removeBand(rows, i))}>
                    Remove
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        <div>
          <Button type="button" variant="secondary" className="min-h-8" onClick={() => setRows(addBand(rows))}>
            Add a band
          </Button>
        </div>
      </section>

      <section aria-labelledby="xp-adjustments" className="flex flex-col gap-2 border-t border-ash pt-3">
        <SectionLabel id="xp-adjustments">Adjustments</SectionLabel>
        <p className="text-xs text-mist">Ticked for a character when awarding a game, such as “Helped +1, once a month” or “Not findable −1”. Leave the limit empty for none.</p>
        {adjustments.map((a, i) => (
          <div key={a.key || i} className="flex flex-wrap items-center gap-2">
            <Input aria-label={`Adjustment ${i + 1}: name`} maxLength={60} value={a.name} onChange={(e) => changeAdjustment(i, { name: e.target.value })} className="w-40" />
            <Input type="number" aria-label={`Adjustment ${i + 1}: XP`} value={a.amount} onChange={(e) => changeAdjustment(i, { amount: e.target.value })} className="w-16" />
            <label className="flex items-center gap-1">
              <Input
                type="number"
                min={1}
                aria-label={`Adjustment ${i + 1}: times a month`}
                value={a.perMonth}
                onChange={(e) => changeAdjustment(i, { perMonth: e.target.value })}
                className="w-16"
              />
              <span className="text-mist">times a month</span>
            </label>
            <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove adjustment ${i + 1}`} onClick={() => setAdjustments(adjustments.filter((_, j) => j !== i))}>
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button type="button" variant="secondary" className="min-h-8" onClick={() => setAdjustments([...adjustments, { key: "", name: "", amount: "1", perMonth: "" }])}>
            Add an adjustment
          </Button>
        </div>
      </section>

      <RadioList
        label="Monthly XP"
        labelClassName="pt-3 text-xs tracking-wide text-mist uppercase"
        className="border-t border-ash pt-3"
        value={cap}
        options={CAPS.map((c) => ({
          value: c.value,
          label: (
            <>
              {c.label}
              {c.value === "warn" && <span className="text-mist"> (the default)</span>}
            </>
          ),
          hint: c.meaning,
        }))}
        onChange={(next) => form.set({ cap: next })}
      >
        <label className="mt-1 flex items-center gap-2">
          <Input
            type="number"
            min={1}
            aria-label="Monthly XP figure"
            placeholder={String(BOOK_MONTHLY)}
            value={monthly}
            disabled={cap === "off"}
            onChange={(e) => form.set({ monthly: e.target.value })}
            className="w-20"
          />
          <span className="text-mist">XP a month (empty for the book's {BOOK_MONTHLY})</span>
        </label>
      </RadioList>

      <fieldset className="flex flex-col gap-2 border-t border-ash pt-3">
        <legend className="pt-3 text-xs tracking-wide text-mist uppercase">Absentee games</legend>
        <Checkbox
          label="Record absentee games"
          hint="A character who missed a game can be marked absentee for it once it has started. It never counts as attended, and gets the chart's absentee XP."
          checked={absentee}
          onChange={(on) => form.set({ absentee: on })}
        />
        <Checkbox
          label="Players can mark their own characters absentee, as well as staff"
          checked={byPlayers}
          disabled={!absentee}
          onChange={(on) => form.set({ byPlayers: on })}
          className={`pl-8 ${absentee ? "" : "opacity-60"}`}
        />
        <Checkbox
          label="Absentee downtimes"
          hint="A character can submit a cycle's downtime only if it attended a game in the lookback before the cycle closes."
          checked={downtime}
          disabled={!absentee}
          onChange={(on) => form.set({ downtime: on })}
          className={`pl-8 ${absentee ? "" : "opacity-60"}`}
        />
        <label className={`flex items-center gap-2 pl-8 ${absentee && downtime ? "" : "opacity-60"}`}>
          <Input
            type="number"
            min={1}
            max={365}
            aria-label="Lookback in days"
            value={lookback}
            disabled={!absentee || !downtime}
            onChange={(e) => form.set({ lookback: e.target.value })}
            className="w-20"
          />
          <span className="text-mist">days back</span>
        </label>
        <p className="text-xs text-mist">{PAYMENTS_NOTE}</p>
      </fieldset>

    </SettingForm>
  );
}

/** For players, on the House rules tab: the troupe's game XP chart, when it has one. */
export function GameXpRules({ troupeId }: { troupeId: string }) {
  const found = useGameXp(troupeId);
  if (!found.data?.bands.length) return null;
  return (
    <Card title="Game XP chart">
      <p className="mb-2 text-sm text-mist">The XP a game gives, by the XP a character has earned in all, not counting starting XP or what joining gave.</p>
      <GameXpChart settings={found.data} />
      {found.data.adjustments.length > 0 && <p className="mt-2 text-sm text-mist">Adjustments: {found.data.adjustments.map(adjustmentText).join("; ")}.</p>}
    </Card>
  );
}
