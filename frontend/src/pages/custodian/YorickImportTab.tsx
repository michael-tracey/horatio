import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Notice, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction, useRulesAction } from "../../hooks";
import { manualLink } from "../../manualLink";
import { categoryWord, OUTCOMES, unmatchedLines, type ReportCharacter, type UnmatchedLine, type YorickImport, type YorickReport } from "./yorickImport";

/** How often a running dry run or import is asked after. */
const POLL = 2000;

/**
 * Bringing a troupe's characters across from Yorick: the custodian uploads the
 * troupe's Print Characters page, checks it with a dry run, puts names to what
 * matched nothing, and imports it as sheeted NPCs of the troupe.
 */
export function YorickImportTab() {
  const [params, setParams] = useSearchParams();
  const troupeId = params.get("troupe") ?? "";
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const underway = useQuery({ queryKey: ["yorick-imports"], queryFn: () => unwrap(api.GET("/api/yorick-imports")) });
  const busy = new Set(underway.data?.map((i) => i.troupe_id));

  return (
    <div className="flex flex-col gap-4">
      <Card title="Import from Yorick">
        <p className="mb-3 text-sm text-mist">
          Bring a troupe's characters across from Yorick as sheeted NPCs of the troupe, for its storytellers to give to each player as they sign up. Upload the
          troupe's <strong className="text-parchment">Print Characters</strong> page, check what the dry run found, and import it when it's ready. A troupe can
          come across over months: upload a newer page whenever you like, and importing again updates the characters made before.{" "}
          <Link to={manualLink("custodian", "importing-characters-from-yorick")} className="text-gold hover:underline">
            How it works
          </Link>
        </p>
        <Field label="Troupe">
          <Select value={troupeId} onChange={(e) => setParams(e.target.value ? { troupe: e.target.value } : {}, { replace: true })} className="max-w-md">
            <option value="">Choose a troupe…</option>
            {troupes.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
                {busy.has(t.id) ? " (import under way)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <ErrorText error={troupes.error ?? underway.error} />
      </Card>
      {troupeId && <ImportPanel key={troupeId} troupeId={troupeId} />}
    </div>
  );
}

function ImportPanel({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const state = useQuery({
    queryKey: ["yorick-import", troupeId],
    queryFn: () => unwrap(api.GET("/api/yorick-imports/{troupe_id}", path)),
    refetchInterval: (q) => (q.state.data?.job ? POLL : false),
  });
  const reportAt = state.data?.report_at;
  const report = useQuery({
    queryKey: ["yorick-import", troupeId, "report", reportAt],
    queryFn: () => unwrap(api.GET("/api/yorick-imports/{troupe_id}/report", path)),
    enabled: !!reportAt,
  });

  if (state.isPending) return <Loading />;
  if (state.error) return <ErrorText error={state.error} />;
  const s = state.data;
  if (!s.uploads_available) {
    return (
      <Card>
        <Notice>Uploads are not set up here, so no page can be uploaded. On the server they are kept in the directory HORATIO_UPLOAD_DIR names.</Notice>
      </Card>
    );
  }
  return (
    <>
      <PageCard state={s} />
      {s.job && <Progress state={s} />}
      {s.error && (
        <p role="alert" className="rounded-md border border-blood/60 bg-blood/15 px-3 py-2 text-sm text-parchment">
          {s.error}
        </p>
      )}
      {report.data && <ReportCards state={s} report={report.data} />}
      <ErrorText error={report.error} />
      <NamesCard state={s} />
      {s.page && <ImportCard state={s} />}
    </>
  );
}

function PageCard({ state }: { state: YorickImport }) {
  const dates = useDates();
  const path = { params: { path: { troupe_id: state.troupe_id } } };
  const input = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState(false);
  const upload = useAction((file: File) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(api.POST("/api/yorick-imports/{troupe_id}/page", { ...path, body: form as never, bodySerializer: (body: unknown) => body as FormData }));
  });
  const remove = useAction(() => unwrap(api.DELETE("/api/yorick-imports/{troupe_id}/page", path)));
  const staff = useAction((userId: string) => unwrap(api.PUT("/api/yorick-imports/{troupe_id}/staff", { ...path, body: { user_id: userId } })));
  const running = !!state.job;

  return (
    <Card
      title="The page"
      actions={
        <span className="flex flex-wrap gap-2">
          <Button type="button" disabled={running || upload.isPending} onClick={() => input.current?.click()}>
            {upload.isPending ? "Uploading…" : state.page ? "Upload a newer page" : "Upload the page"}
          </Button>
          {state.page && (
            <Button type="button" variant="danger" disabled={running} onClick={() => setDeleting(true)}>
              Delete the page
            </Button>
          )}
        </span>
      }
    >
      <input
        ref={input}
        type="file"
        accept=".zip,.html,.htm,application/zip,text/html"
        aria-label="Print Characters page"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      {state.page ? (
        <p className="mb-3 text-sm">
          <span className="text-parchment">{state.page.name}</span>
          <span className="text-mist">
            {" "}
            · uploaded {dates.dateTime(state.page.uploaded_at)}
            {state.page.uploaded_by ? ` by @${state.page.uploaded_by}` : ""} · deleted on {dates.date(state.page.expires_at)} if not imported by then
          </span>
        </p>
      ) : (
        <p className="mb-3 text-sm text-mist">No page uploaded{state.report_kind === "import" ? ": the last one was imported, and deleted" : ""}.</p>
      )}
      <p className="mb-3 text-sm text-mist">
        In Yorick, open the troupe's <strong className="text-parchment">Print Characters</strong> page and save it from the browser as a complete web page. That
        gives an .html file and a folder of the same name ending in <code>_files</code>, which holds the portraits. Zip the two together and upload the zip; the
        .html alone works too, without portraits. The page holds players' names and emails: it's kept only for this import, seen only by you, and deleted once
        imported, when you delete it, or after 30 days.
      </p>
      <Field label="The NPCs are made by" hint="Imported NPCs are made by this storyteller, as if they had made them.">
        <Select value={state.staff_id} disabled={running || staff.isPending} onChange={(e) => staff.mutate(e.target.value)} className="max-w-md">
          {state.staff.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name} (@{p.handle}){p.lead ? ", lead storyteller" : ""}
            </option>
          ))}
        </Select>
      </Field>
      <ErrorText error={upload.error ?? remove.error ?? staff.error} />
      <Dialog title="Delete the uploaded page?" open={deleting} onClose={() => setDeleting(false)}>
        <p className="mb-4 text-sm">
          The page and the report from it are deleted now. The troupe's names and your choices stay, for the next page you upload.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => setDeleting(false)}>
            Keep it
          </Button>
          <Button
            type="button"
            variant="danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(undefined, { onSuccess: () => setDeleting(false) })}
          >
            Delete it
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}

function Progress({ state }: { state: YorickImport }) {
  const job = state.job!;
  const what = job.kind === "import" ? "Importing" : "Dry run";
  return (
    <Card>
      <p role="status" className="mb-2 text-sm">
        {what}: {job.total ? `${job.done} of ${job.total} characters…` : "starting…"} This takes a minute or two for a big troupe; you can leave this page and
        come back.
      </p>
      <progress className="h-2 w-full accent-gold" max={job.total || 1} value={job.done} aria-label={`${what} progress`} />
    </Card>
  );
}

function ReportCards({ state, report }: { state: YorickImport; report: YorickReport }) {
  const dates = useDates();
  const path = { params: { path: { troupe_id: state.troupe_id } } };
  const again = useAction(() => unwrap(api.POST("/api/yorick-imports/{troupe_id}/dry-run", path)));
  const dry = report.kind === "dry_run";
  const shared = report.characters.filter((c) => c.matches.length);
  const { waiting, handed } = unmatchedLines(report.characters, state.by_hand);

  return (
    <>
      <Card
        title={dry ? "Dry run" : "Imported"}
        actions={
          state.page && (
            <Button type="button" variant="secondary" disabled={!!state.job || again.isPending} onClick={() => again.mutate(undefined)}>
              Run the dry run again
            </Button>
          )
        }
      >
        <p className="mb-2 text-xs text-mist">
          {dry ? "Checked" : "Imported"} {dates.dateTime(report.at)}. {dry ? "Nothing was saved." : ""} The report is deleted on{" "}
          {state.report_expires_at ? dates.date(state.report_expires_at) : "—"}.
        </p>
        {report.stale && <Notice>Names or choices have changed since: run the dry run again to see what the import will do now.</Notice>}
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {report.summary.slice(0, report.summary.indexOf("") === -1 ? undefined : report.summary.indexOf("")).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p className="mt-3 flex flex-wrap gap-4 text-sm">
          <a href={`/api/yorick-imports/${state.troupe_id}/report.txt`} download className="text-gold hover:underline">
            Download the report
          </a>
          <a href={`/api/yorick-imports/${state.troupe_id}/characters.json`} download className="text-gold hover:underline">
            Download the characters as JSON
          </a>
        </p>
        <ErrorText error={again.error} />
      </Card>
      {shared.length > 0 && <SharedNames state={state} characters={shared} />}
      {(waiting.length > 0 || handed.length > 0) && <UnmatchedCard state={state} waiting={waiting} handed={handed} />}
      <CharactersCard report={report} />
    </>
  );
}

/** Printed characters whose name a character here has: overwrite it, skip, or import beside it. */
function SharedNames({ state, characters }: { state: YorickImport; characters: ReportCharacter[] }) {
  const choices = new Map(state.decisions.map((d) => [d.legacy_id, d]));
  return (
    <Card title="Already here under the same name">
      <p className="mb-3 text-sm text-mist">
        Each of these has the name of a character already in the troupe, not one this import made. Choose what to do with each before importing. Only one of the
        troupe's sheeted NPCs can be overwritten: a player's character changes through the troupe's approvals.
      </p>
      <ul className="divide-y divide-ash">
        {characters.map((c) => (
          <SharedName key={c.legacy_id} state={state} character={c} chosen={choices.get(c.legacy_id)} />
        ))}
      </ul>
    </Card>
  );
}

function SharedName({ state, character, chosen }: { state: YorickImport; character: ReportCharacter; chosen?: YorickImport["decisions"][number] }) {
  const decide = useAction((value: string) => {
    const [choice, characterId] = value.split(":");
    return unwrap(
      api.PUT("/api/yorick-imports/{troupe_id}/decisions/{legacy_id}", {
        params: { path: { troupe_id: state.troupe_id, legacy_id: character.legacy_id } },
        body: { choice: (choice || null) as "overwrite" | "skip" | "new" | null, character_id: characterId || null },
      }),
    );
  });
  const value = chosen ? (chosen.choice === "overwrite" ? `overwrite:${chosen.character_id}` : chosen.choice) : "";
  const id = useId();
  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="text-sm">
        <span id={id} className="text-parchment">
          {character.name}
        </span>
        {!chosen && (
          <Badge tone="blood" className="ml-2">
            Needs a choice
          </Badge>
        )}
        <ul className="mt-1 text-xs text-mist">
          {character.matches.map((m) => (
            <li key={m.character_id}>
              Here:{" "}
              <Link to={`/characters/${m.character_id}`} className="text-gold hover:underline">
                {m.name}
              </Link>
              , {m.whose}
            </li>
          ))}
        </ul>
        <ErrorText error={decide.error} />
      </div>
      <Select aria-labelledby={id} value={value} disabled={!!state.job || decide.isPending} onChange={(e) => decide.mutate(e.target.value)} className="sm:w-72">
        <option value="">Choose…</option>
        {character.matches
          .filter((m) => m.overwritable)
          .map((m) => (
            <option key={m.character_id} value={`overwrite:${m.character_id}`}>
              Overwrite {m.name}
              {character.matches.length > 1 ? ` (${m.whose})` : ""}
            </option>
          ))}
        <option value="skip">Skip it</option>
        <option value="new">Import it as a new NPC beside it</option>
      </Select>
    </li>
  );
}

function UnmatchedCard({ state, waiting, handed }: { state: YorickImport; waiting: UnmatchedLine[]; handed: UnmatchedLine[] }) {
  const [matching, setMatching] = useState<UnmatchedLine | null>(null);
  return (
    <Card title="Printed lines that matched nothing">
      <p className="mb-3 text-sm text-mist">
        Give each a name of Horatio's with <strong className="text-parchment">Match to…</strong>: it's kept in the troupe's names, for every character that printed
        it, and for later pages. Or leave it for the troupe's staff to put right on the sheets by hand. Then run the dry run again.
      </p>
      {waiting.length ? (
        <ul className="divide-y divide-ash">
          {waiting.map((line) => (
            <UnmatchedRow key={line.source} state={state} line={line} onMatch={() => setMatching(line)} />
          ))}
        </ul>
      ) : (
        <Empty>Every line is matched, or left for staff.</Empty>
      )}
      {handed.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm text-mist">Left for staff to put right by hand ({handed.length})</summary>
          <ul className="divide-y divide-ash">
            {handed.map((line) => (
              <UnmatchedRow key={line.source} state={state} line={line} onMatch={() => setMatching(line)} handed />
            ))}
          </ul>
        </details>
      )}
      <Dialog title="Match to…" open={!!matching} onClose={() => setMatching(null)}>
        {matching && <MatchForm state={state} line={matching} onDone={() => setMatching(null)} />}
      </Dialog>
    </Card>
  );
}

function UnmatchedRow({ state, line, onMatch, handed = false }: { state: YorickImport; line: UnmatchedLine; onMatch: () => void; handed?: boolean }) {
  const mark = useAction((byHand: boolean) =>
    unwrap(api.PUT("/api/yorick-imports/{troupe_id}/by-hand", { params: { path: { troupe_id: state.troupe_id } }, body: { source: line.source, by_hand: byHand } })),
  );
  const count = line.characters.length;
  return (
    <li className="flex flex-col gap-2 py-2 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <span className="text-parchment">{line.source}</span>
        <span className="block text-xs text-mist">
          {line.reason} · {count === 1 ? line.characters[0] : `${count} characters`}
        </span>
        <ErrorText error={mark.error} />
      </div>
      <span className="flex shrink-0 flex-wrap gap-2">
        {line.part && (
          <Button type="button" variant="secondary" disabled={!!state.job} onClick={onMatch} aria-label={`Match ${line.source} to…`}>
            Match to…
          </Button>
        )}
        <Button type="button" variant="ghost" disabled={mark.isPending} onClick={() => mark.mutate(!handed)}>
          {handed ? "Not by hand" : "Staff will fix by hand"}
        </Button>
      </span>
    </li>
  );
}

function MatchForm({ state, line, onDone }: { state: YorickImport; line: UnmatchedLine; onDone: () => void }) {
  const part = line.part!;
  const options = useQuery({
    queryKey: ["yorick-import", state.troupe_id, "options", part, line.category],
    queryFn: () => unwrap(api.GET("/api/yorick-imports/{troupe_id}/options", { params: { path: { troupe_id: state.troupe_id }, query: { part, category: line.category } } })),
  });
  const [chosen, setChosen] = useState("");
  const listId = useId();
  const save = useAction((horatio: string) =>
    unwrap(
      api.PUT("/api/yorick-imports/{troupe_id}/names", {
        params: { path: { troupe_id: state.troupe_id } },
        body: { part, category: line.category, yorick: line.key, horatio },
      }),
    ),
  );
  const valid = !!options.data?.includes(chosen);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) save.mutate(chosen, { onSuccess: onDone });
      }}
      className="flex flex-col gap-3"
    >
      <p className="text-sm">
        Yorick's <strong>“{line.key}”</strong>, as a {categoryWord(line.category)}, is Horatio's:
      </p>
      {options.isPending ? (
        <Loading />
      ) : options.data?.length ? (
        <Field label={`Horatio's ${categoryWord(line.category)}`} hint={`${options.data.length} to choose from; type to narrow them.`}>
          <Input list={listId} value={chosen} onChange={(e) => setChosen(e.target.value)} autoFocus />
        </Field>
      ) : (
        <Notice>There's nothing to choose from here: the troupe keeps no list of these. Leave it for staff instead.</Notice>
      )}
      <datalist id={listId}>
        {options.data?.map((o) => (
          <option key={o} value={o} />
        ))}
      </datalist>
      <ErrorText error={options.error ?? save.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!valid || save.isPending}>
          Match
        </Button>
      </div>
    </form>
  );
}

function CharactersCard({ report }: { report: YorickReport }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = report.characters.filter((c) => !q || c.name.toLowerCase().includes(q));
  const dry = report.kind === "dry_run";
  return (
    <Card title={`Each character (${report.characters.length})`}>
      <Input type="search" aria-label="Find a character" placeholder="Name…" value={query} onChange={(e) => setQuery(e.target.value)} className="mb-3 max-w-sm" />
      <ul className="divide-y divide-ash">
        {shown.map((c) => (
          <li key={c.legacy_id} className="py-2">
            <details>
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm">
                <span className="text-parchment">{c.name}</span>
                {c.label && <span className="text-xs text-mist">{c.label}</span>}
                <Badge tone={OUTCOMES[c.outcome].tone}>{dry ? OUTCOMES[c.outcome].dry : OUTCOMES[c.outcome].done}</Badge>
                {c.unmatched.length + c.refused.length > 0 && <span className="text-xs text-mist">{c.unmatched.length + c.refused.length} lines unmatched</span>}
                {c.problems.length > 0 && <span className="text-xs text-mist">{c.problems.length} rule checks</span>}
              </summary>
              <CharacterDetail character={c} />
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function CharacterDetail({ character: c }: { character: ReportCharacter }) {
  const sections: [string, string[]][] = [
    ["Matched nothing", c.unmatched.map((u) => `${u.source} (${u.reason})`)],
    ["Couldn't be put on the sheet", c.refused],
    ["Held at Horatio's value", c.revalued],
    ["Read as several", c.split],
    ["Rule checks the sheet breaks", c.problems],
    ["No price in this troupe", c.unpriced],
    ["Left to staff", c.left_out],
  ];
  return (
    <div className="mt-2 flex flex-col gap-2 pl-3 text-sm">
      {c.skipped_because && <p className="text-mist">{c.skipped_because.charAt(0).toUpperCase() + c.skipped_because.slice(1)}.</p>}
      {c.character_id && (
        <p>
          <Link to={`/characters/${c.character_id}`} className="text-gold hover:underline">
            Its sheet here
          </Link>
        </p>
      )}
      {!["skipped", "undecided", "failed"].includes(c.outcome) && (
        <p className="text-mist">
          {c.traits} traits · {c.xp} XP at the troupe's prices · portrait: {c.portrait}
        </p>
      )}
      {sections
        .filter(([, items]) => items.length)
        .map(([title, items]) => (
          <div key={title}>
            <h3 className="text-xs uppercase tracking-wide text-mist">{title}</h3>
            <ul className="list-disc pl-5">
              {items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}

function NamesCard({ state }: { state: YorickImport }) {
  const path = { params: { path: { troupe_id: state.troupe_id } } };
  const input = useRef<HTMLInputElement>(null);
  const remove = useAction((n: YorickImport["names"][number]) =>
    unwrap(api.PUT("/api/yorick-imports/{troupe_id}/names", { ...path, body: { part: n.part, category: n.category, yorick: n.yorick, horatio: null } })),
  );
  const add = useAction((file: File) => {
    const form = new FormData();
    form.append("file", file);
    return unwrap(api.POST("/api/yorick-imports/{troupe_id}/names/file", { ...path, body: form as never, bodySerializer: (body: unknown) => body as FormData }));
  });
  return (
    <Card
      title="The troupe's names"
      actions={
        <Button type="button" variant="secondary" disabled={!!state.job || add.isPending} onClick={() => input.current?.click()}>
          Add from a table…
        </Button>
      }
    >
      <p className="mb-3 text-sm text-mist">
        What Yorick's printout calls something, and what Horatio calls it, for this troupe, on top of the names every troupe shares. They stay between pages. A
        table written for the old command-line import (a .toml file) can be added here.
      </p>
      <input
        ref={input}
        type="file"
        accept=".toml,text/plain"
        aria-label="Table of names"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) add.mutate(file);
        }}
      />
      {add.data && (
        <p role="status" className="mb-2 text-sm text-gold">
          Added {add.data.added} names. Run the dry run again to use them.
        </p>
      )}
      {state.names.length ? (
        <ul className="divide-y divide-ash text-sm">
          {state.names.map((n) => (
            <li key={`${n.part}/${n.category}/${n.yorick}`} className="flex items-center justify-between gap-2 py-1.5">
              <span className="min-w-0">
                “{n.yorick}” → <span className="text-parchment">{n.horatio}</span> <span className="text-xs text-mist">({categoryWord(n.category)})</span>
              </span>
              <Button type="button" variant="ghost" aria-label={`Remove ${n.yorick}`} disabled={!!state.job || remove.isPending} onClick={() => remove.mutate(n)}>
                ×
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>None yet.</Empty>
      )}
      <ErrorText error={remove.error ?? add.error} />
    </Card>
  );
}

function ImportCard({ state }: { state: YorickImport }) {
  const [confirming, setConfirming] = useState(false);
  const [withoutBackup, setWithoutBackup] = useState(false);
  const run = useRulesAction(() =>
    unwrap(api.POST("/api/yorick-imports/{troupe_id}/import", { params: { path: { troupe_id: state.troupe_id } }, body: { without_backup: withoutBackup } })),
  );
  const blocked = state.cannot_import ?? (!state.backups_available && !withoutBackup ? "Backups are not set up here: tick to go ahead without one." : null);
  return (
    <Card title="Import">
      <p className="mb-3 text-sm text-mist">
        The import makes a backup first, then saves every character at once, or none if one fails. Each becomes a sheeted NPC of {state.troupe_name}, flagged
        wherever its sheet breaks a rule check. Nothing is given to players and no XP is written: that happens when a storyteller gives each one to its player.
        Afterwards the page is deleted.
      </p>
      {!state.backups_available && (
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={withoutBackup} onChange={(e) => setWithoutBackup(e.target.checked)} />
          Backups aren't set up on this server: import without one
        </label>
      )}
      {blocked && <p className="mb-3 text-sm text-mist">{blocked}</p>}
      <Button type="button" disabled={!!blocked || run.isPending} onClick={() => setConfirming(true)}>
        Import into {state.troupe_name}
      </Button>
      <ErrorText error={run.error} />
      <Dialog title={`Import into ${state.troupe_name}?`} open={confirming} onClose={() => setConfirming(false)}>
        <p className="mb-4 text-sm">
          The characters the dry run found are saved as NPCs of {state.troupe_name}, as the dry run showed. {state.backups_available ? "A backup is made first." : ""}
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => setConfirming(false)}>
            Not yet
          </Button>
          <Button type="button" disabled={run.isPending} onClick={() => run.mutate(undefined, { onSuccess: () => setConfirming(false) })}>
            Import
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}
