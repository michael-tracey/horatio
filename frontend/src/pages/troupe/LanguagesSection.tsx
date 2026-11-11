import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { LanguagesOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Input, Loading } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { chartFor, LANGUAGE_MODES, type LanguageMode, ratingsOf, readFigures, startingFigures } from "./languages";

type Choice = { mode: LanguageMode; custom: number[] | null; natural_doubles: boolean };

/**
 * How many languages Linguistics gives in the troupe: the book's one per dot, the
 * accelerated chart or the troupe's own, and whether Natural Linguist doubles it.
 * Creation, purchases and sheets follow at once; characters already holding more
 * than a new chart allows keep them, and are listed here.
 */
export function LanguagesSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const toast = useToast();
  const languages = useQuery({ queryKey: ["languages", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/languages", path)) });
  const save = useRulesAction((body: Choice) => unwrap(api.PUT("/api/troupes/{troupe_id}/languages", { ...path, body })));
  if (languages.isPending) return <Loading />;
  if (languages.error) return <ErrorText error={languages.error} />;
  return (
    <LanguagesForm
      key={`${languages.data.mode}/${languages.data.custom.join(",")}/${languages.data.natural_doubles}`}
      data={languages.data}
      canEdit={canEdit}
      saving={save.isPending}
      error={save.error}
      onSave={(choice) => save.mutate(choice, { onSuccess: () => toast({ message: "Saved: how many languages Linguistics gives" }) })}
    />
  );
}

/** The setting itself, from what the server says it is now. */
export function LanguagesForm({
  data,
  canEdit,
  saving = false,
  error = null,
  onSave,
}: {
  data: LanguagesOut;
  canEdit: boolean;
  saving?: boolean;
  error?: unknown;
  onSave: (choice: Choice) => void;
}) {
  const [mode, setMode] = useState<LanguageMode>(data.mode);
  const [figures, setFigures] = useState<string[]>(() => startingFigures(data));
  const [doubles, setDoubles] = useState(data.natural_doubles);
  const read = readFigures(figures);
  const chart = chartFor(mode, data.accelerated, read.table);
  const ratings = ratingsOf(chart, data.max_rating);
  const customChanged = read.table !== null && read.table.join(",") !== data.custom.join(",");
  const changed = mode !== data.mode || doubles !== data.natural_doubles || (mode === "custom" && customChanged);
  const blocked = mode === "custom" && read.error !== null;

  return (
    <div className="flex flex-col gap-6">
      <Card title="Languages from Linguistics">
        <p className="mb-3 text-sm text-mist">
          By the book each dot of Linguistics gives one language (p. 94), and Natural Linguist two (p. 252). A troupe can play a chart instead. Creation, purchases and sheets
          follow the troupe&apos;s choice straight away.
        </p>
        {!canEdit ? (
          <>
            <p className="text-sm">{data.text[0]?.toUpperCase() + data.text.slice(1)}.</p>
            <Chart ratings={data.table} doubled={data.natural_doubles} className="mt-3" />
          </>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (blocked) return;
              onSave({ mode, custom: mode === "custom" ? read.table : null, natural_doubles: doubles });
            }}
          >
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm text-mist">How many languages does each rating of Linguistics give?</legend>
              {LANGUAGE_MODES.map((m) => (
                <label key={m.value} className="flex items-start gap-2 text-sm">
                  <input type="radio" name="languages-mode" className="mt-1" checked={mode === m.value} onChange={() => setMode(m.value)} />
                  <span>
                    {m.label}
                    <span className="block text-xs text-mist">{m.meaning}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {mode === "custom" && (
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 text-sm text-mist">
                  Languages at each rating. Ratings above 5 need a merit or more Generation; the last figure carries on above.
                </legend>
                <div className="grid grid-cols-5 gap-2 sm:grid-cols-10">
                  {figures.map((f, i) => (
                    <label key={i} className="flex flex-col gap-1 text-xs text-mist">
                      {i + 1}
                      <Input
                        aria-label={`Languages at Linguistics ${i + 1}`}
                        inputMode="numeric"
                        value={f}
                        onChange={(e) => setFigures(figures.map((g, j) => (j === i ? e.target.value : g)))}
                        className="min-h-8 px-2 py-1 text-sm"
                      />
                    </label>
                  ))}
                </div>
                {read.error && <p className="text-sm text-blood-bright">{read.error}</p>}
              </fieldset>
            )}
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={doubles} onChange={(e) => setDoubles(e.target.checked)} />
              <span>
                Natural Linguist doubles it
                <span className="block text-xs text-mist">As the book has it: a character with Natural Linguist holds twice as many languages (p. 252).</span>
              </span>
            </label>
            {!blocked && <Chart ratings={ratings} doubled={doubles} />}
            <div className="flex gap-2">
              <Button type="submit" disabled={!changed || blocked || saving}>
                Save
              </Button>
            </div>
            <ErrorText error={error} />
          </form>
        )}
      </Card>
      {data.over.length > 0 && (
        <Card title="Holding more than the chart allows">
          <p className="mb-2 text-sm text-mist">These characters keep their languages. Their sheets show the rule they break, for you to settle with their players.</p>
          <ul className="divide-y divide-ash">
            {data.over.map((o) => (
              <li key={o.character_id} className="flex items-baseline justify-between gap-2 py-2 text-sm">
                <Link to={`/characters/${o.character_id}`} className="text-parchment hover:text-gold">
                  {o.name}
                </Link>
                <span className="text-gold">
                  {o.held} of {o.allowed} languages
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/** A chart of languages by rating of Linguistics, with Natural Linguist's where it doubles them. */
export function Chart({ ratings, doubled, className = "" }: { ratings: number[]; doubled: boolean; className?: string }) {
  return (
    <div className={`overflow-x-auto ${className}`}>
      <table className="text-sm">
        <caption className="sr-only">Languages at each rating of Linguistics</caption>
        <tbody>
          <tr>
            <th scope="row" className="pr-3 text-left font-normal text-mist">
              Linguistics
            </th>
            {ratings.map((_, i) => (
              <td key={i} className="px-1.5 text-center text-mist">
                {i + 1}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className="pr-3 text-left font-normal text-mist">
              Languages
            </th>
            {ratings.map((n, i) => (
              <td key={i} className="px-1.5 text-center text-parchment">
                {n}
              </td>
            ))}
          </tr>
          {doubled && (
            <tr>
              <th scope="row" className="pr-3 text-left font-normal whitespace-nowrap text-mist">
                With Natural Linguist
              </th>
              {ratings.map((n, i) => (
                <td key={i} className="px-1.5 text-center text-parchment">
                  {n * 2}
                </td>
              ))}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
