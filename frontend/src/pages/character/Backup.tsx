import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BackupXpOut, CharacterOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Loading, Notice, PageTitle } from "../../components/ui";
import { useAction } from "../../hooks";
import { BuildFor } from "./BuildFor";
import { MAX_BYTES, SECTIONS, STATUS, backupFileName, countsText, reviewCounts, sectionsQuery, type Section } from "./backup";

/** Ticks for the optional sections of a backup. */
export function SectionTicks({ chosen, onChange }: { chosen: ReadonlySet<Section>; onChange: (next: Set<Section>) => void }) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-sm text-mist">Also include</legend>
      {SECTIONS.map((s) => (
        <label key={s.key} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={chosen.has(s.key)}
            onChange={(e) => {
              const next = new Set(chosen);
              if (e.target.checked) next.add(s.key);
              else next.delete(s.key);
              onChange(next);
            }}
          />
          {s.label}
        </label>
      ))}
    </fieldset>
  );
}

function save(blob: Blob, name: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

/**
 * Export (backup), from a character's ⋯ menu (#567): its file, to keep or to import
 * into another troupe or another Horatio, and its printable sheet as a page that reads
 * without Horatio. Retired characters can be exported too.
 */
export function ExportBackup({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const [chosen, setChosen] = useState<Set<Section>>(new Set());
  const download = useMutation({
    mutationFn: async () => {
      const found = await unwrap(
        api.GET("/api/characters/{character_id}/backup", { params: { path: { character_id: character.id }, query: { sections: [...chosen] } } }),
      );
      save(new Blob([JSON.stringify(found, null, 2)], { type: "application/json" }), backupFileName(character.name, new Date()));
    },
  });
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        A file of {character.name}'s sheet, free dots, XP history, backstory and picture. Keep it as a backup, or import it as a new character in another troupe or another
        Horatio. Staff notes are never in it.
      </p>
      <SectionTicks chosen={chosen} onChange={setChosen} />
      <ErrorText error={download.error} />
      <div className="flex flex-wrap justify-end gap-2">
        <a
          href={`/api/characters/${character.id}/backup/sheet`}
          download
          className="inline-flex min-h-10 items-center justify-center rounded-md border border-ash px-4 text-sm text-parchment hover:border-mist"
        >
          Printable sheet (.html)
        </a>
        <Button disabled={download.isPending} onClick={() => download.mutate(undefined, { onSuccess: onDone })}>
          {download.isPending ? "Exporting…" : "Download backup"}
        </Button>
      </div>
      <p className="text-right text-xs text-mist">{backupFileName(character.name, new Date())}</p>
    </div>
  );
}

/**
 * The troupe's characters and NPCs in one .zip (#567), from its character list: all,
 * its player characters or NPCs only, or those ticked; with the optional sections, and
 * for storytellers, players' emails beside their handles.
 */
export function TroupeExport({ troupeId, selected, canEmail }: { troupeId: string; selected: string[]; canEmail: boolean }) {
  type Which = "all" | "pcs" | "npcs" | "selected";
  const [which, setWhich] = useState<Which>("all");
  const [chosen, setChosen] = useState<Set<Section>>(new Set());
  const [emails, setEmails] = useState(false);
  const extra: Record<string, string> = which === "selected" ? {} : { which };
  if (emails && canEmail) extra.emails = "true";
  let href = `/api/troupes/${troupeId}/character-backups${sectionsQuery(chosen, extra)}`;
  if (which === "selected") href += `${href.includes("?") ? "&" : "?"}${selected.map((id) => `characters=${id}`).join("&")}`;
  const options: { key: Which; label: string }[] = [
    { key: "all", label: "Every character and NPC" },
    { key: "pcs", label: "Player characters" },
    { key: "npcs", label: "NPCs" },
    ...(selected.length ? [{ key: "selected" as const, label: `The ${selected.length} selected` }] : []),
  ];
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-mist">
        A .zip of the troupe's own characters (not visitors), each as a file Horatio can import, with its picture and printable sheet. Staff notes are never in it.
      </p>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm text-mist">Export</legend>
        {options.map((o) => (
          <label key={o.key} className="flex items-center gap-2 text-sm">
            <input type="radio" name="export-which" checked={which === o.key} onChange={() => setWhich(o.key)} />
            {o.label}
          </label>
        ))}
      </fieldset>
      <SectionTicks chosen={chosen} onChange={setChosen} />
      {canEmail && (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={emails} onChange={(e) => setEmails(e.target.checked)} />
          <span>
            Include players' emails
            <span className="block text-xs text-mist">Handles are always in it. Emails are personal: add them only to match characters to their players on import.</span>
          </span>
        </label>
      )}
      <div className="flex justify-end">
        <a href={href} download className="inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-5 text-sm font-medium text-parchment hover:bg-blood-bright">
          Download .zip
        </a>
      </div>
    </div>
  );
}

// --- importing ------------------------------------------------------------------------------

type Loaded = { document: Record<string, unknown>; fileName: string };

/**
 * Import a character (#567), from Your characters: choose a file exported from Horatio
 * and the troupe it is for, review what comes in, then import it as a new character of
 * yours, not yet in any troupe. Its XP history comes as self-entered XP, which the
 * troupe that accepts it keeps or removes.
 */
export function ImportCharacterPage() {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [troupeId, setTroupeId] = useState<string | null>(null);
  return (
    <>
      <PageTitle subtitle="Bring in a character exported from Horatio: a backup of yours, or one from another Horatio.">Import a character</PageTitle>
      <div className="flex max-w-3xl flex-col gap-6">
        <Card>
          <div className="flex flex-col gap-4">
            <ChooseFile loaded={loaded} onLoad={setLoaded} />
            <BuildFor value={troupeId} onChange={setTroupeId} />
          </div>
        </Card>
        {loaded && <Review key={`${loaded.fileName}:${troupeId ?? ""}`} loaded={loaded} troupeId={troupeId} />}
      </div>
    </>
  );
}

function ChooseFile({ loaded, onLoad }: { loaded: Loaded | null; onLoad: (found: Loaded) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const read = async (file: File) => {
    setProblem(null);
    if (file.size > MAX_BYTES) return setProblem("That file is too large to be a Horatio character.");
    try {
      onLoad({ document: JSON.parse(await file.text()) as Record<string, unknown>, fileName: file.name });
    } catch {
      setProblem("That file isn't a Horatio character: choose a .horatio-character.json file exported from Horatio.");
    }
  };
  return (
    <div className="flex flex-col gap-2">
      <input
        ref={input}
        type="file"
        accept=".json,application/json"
        aria-label="Character file"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void read(file);
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="secondary" onClick={() => input.current?.click()}>
          {loaded ? "Choose another file…" : "Choose a file…"}
        </Button>
        {loaded && <span className="text-sm text-mist">{loaded.fileName}</span>}
      </div>
      {problem && <ErrorText error={problem} />}
    </div>
  );
}

function Review({ loaded, troupeId }: { loaded: Loaded; troupeId: string | null }) {
  const navigate = useNavigate();
  const toast = useToast();
  const body = { document: loaded.document as Record<string, never>, troupe_id: troupeId, file_name: loaded.fileName };
  const check = useMutation({ mutationFn: () => unwrap(api.POST("/api/characters/import/review", { body })) });
  const apply = useAction(() => unwrap(api.POST("/api/characters/import", { body })), [["characters"]]);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    // Once, as it loads: a new file or troupe makes a new review.
    check.mutate();
  }, []);

  if (check.error) return <ErrorText error={check.error} />;
  if (!check.data) return <Loading />;
  const review = check.data;
  const counts = reviewCounts(review);
  return (
    <Card title={`Review ${review.name}`}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-mist">
          {review.from_troupe ? `From ${review.from_troupe}` : "From outside any troupe"}
          {review.exported_on && `, exported on ${review.exported_on}`}. It comes in as a new character of yours, {review.troupe ? `built for ${review.troupe}` : "on the book's rules"}
          , and joins no troupe until you ask one to make it home.
        </p>
        {review.warnings.map((w) => (
          <Notice key={w}>{w}</Notice>
        ))}
        {review.xp && <XpFigures xp={review.xp} troupe={review.troupe} from={review.from_troupe} />}
        <div role="group" aria-label="What comes in" className="flex flex-col gap-3">
          {review.parts.map((part) => (
            <section key={part.key} className="rounded-lg border border-ash p-3">
              <h3 className="text-gold">{part.label}</h3>
              <ul className="divide-y divide-ash">
                {part.items.map((item, i) => (
                  <li key={i} className="flex flex-col gap-1 py-2 text-sm">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <span className="min-w-0 break-words text-parchment">{item.label}</span>
                      <Badge tone={STATUS[item.status].tone}>{STATUS[item.status].label}</Badge>
                    </div>
                    {item.status === "differs" && (
                      <p className="text-xs text-mist">
                        In the file: {item.before}; here: <span className="text-parchment">{item.after}</span>
                      </p>
                    )}
                    {item.reason && <p className={`text-xs ${item.status === "cannot" ? "text-blood-bright" : "text-mist"}`}>{item.reason}</p>}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="flex flex-col gap-2 border-t border-ash pt-4">
          <p className="text-sm" role="status">
            {countsText(counts)}.
          </p>
          <ErrorText error={apply.error} />
          <div>
            <Button
              disabled={apply.isPending}
              onClick={() =>
                apply.mutate(undefined, {
                  onSuccess: (done) => {
                    toast({ message: `Imported ${done.name}` });
                    navigate(`/characters/${done.character_id}`);
                  },
                })
              }
            >
              {apply.isPending ? "Importing…" : `Import ${review.name}`}
            </Button>
          </div>
          <p className="text-xs text-mist">
            Changed your mind? <Link to="/characters" className="underline hover:text-parchment">Back to your characters</Link>
          </p>
        </div>
      </div>
    </Card>
  );
}

function XpFigures({ xp, troupe, from }: { xp: BackupXpOut; troupe: string | null; from: string }) {
  const here = troupe ? `${troupe}'s prices` : "the book's prices";
  return (
    <section aria-label="XP" className="rounded-lg border border-ash p-3 text-sm">
      <h3 className="mb-2 text-gold">XP</h3>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        <dt className="text-mist">Earned, in the file</dt>
        <dd className="text-right">{xp.earned}</dd>
        <dt className="text-mist">Spent</dt>
        <dd className="text-right">{xp.spent}</dd>
        {xp.lost > 0 && (
          <>
            <dt className="text-mist">Lost</dt>
            <dd className="text-right">{xp.lost}</dd>
          </>
        )}
        <dt className="text-mist">Unspent</dt>
        <dd className="text-right">{xp.unspent}</dd>
        <dt className="text-mist">The sheet cost {from ? `in ${from}` : "where it came from"}</dt>
        <dd className="text-right">{xp.sheet_there}</dd>
        <dt className="text-mist">The sheet costs at {here}</dt>
        <dd className={`text-right ${xp.sheet_here !== xp.sheet_there ? "text-gold" : ""}`}>{xp.sheet_here}</dd>
      </dl>
      {xp.unpriced.length > 0 && <p className="mt-2 text-xs text-mist">Not priced at {here}: {xp.unpriced.join(", ")}.</p>}
      <p className="mt-2 text-xs text-mist">
        Nothing is repriced. The {xp.self_entered} XP earned comes in as self-entered XP: the troupe that accepts the character keeps or removes it, and settles any difference
        in price when you ask it to make the character home.
      </p>
    </section>
  );
}
