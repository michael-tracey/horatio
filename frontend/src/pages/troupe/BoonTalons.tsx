import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BoonTalonsOut, TalonOut, TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

type Word = NonNullable<TroupeOut["boon_talon_word"]>;
type Can = { can_add: boolean; can_edit: boolean; can_audit: boolean };

/** One of them, as "a Lesser Harpy". */
export function oneOf(word: string) {
  return word === "Talons" ? "Talon" : "Lesser Harpy";
}

const NONE: Can = { can_add: false, can_edit: false, can_audit: false };

const ABILITIES: { key: keyof Can; label: string; hint: string }[] = [
  { key: "can_add", label: "Add boons", hint: "Register boons in the ledger." },
  {
    key: "can_edit",
    label: "Edit boons",
    hint: "Edit, trade, pass on, settle, void and reopen boons, and review what players report.",
  },
  {
    key: "can_audit",
    label: "Perform audits",
    hint: "Audit a character's boons.",
  },
];

/** What a Lesser Harpy may do, in words. */
function what(t: Can) {
  const parts = ["sees the ledger"];
  if (t.can_add) parts.push("adds boons");
  if (t.can_edit) parts.push(t.can_add ? "edits them" : "edits boons");
  if (t.can_audit) parts.push("performs audits");
  return parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

function useTalons(troupeId: string) {
  return useQuery({
    queryKey: ["boon-talons", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/boon-talons", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
}

/**
 * Whether the Harpy may give others access to the ledger (#689), and what the troupe
 * calls them: Lesser Harpies or Talons. Only while the Harpy has the full ledger. With
 * it on, staff see who has what, and may take it away.
 */
export function TalonsSetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  // Shown as chosen at once, while it saves.
  const [on, setOn] = useState(troupe.boon_talons ?? false);
  const [word, setWord] = useState<Word>(troupe.boon_talon_word ?? "Lesser Harpies");
  const full = troupe.boon_harpy === "full";
  const save = useAction(async (next: { on: boolean; word: Word }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-talons-setting", { params: { path: { troupe_id: troupe.id } }, body: next }));
    toast({ message: next.on ? `Saved: the Harpy may give others access to the ledger, as ${next.word}.` : "Saved: the Harpy gives no one access." });
  });
  const choose = (next: { on: boolean; word: Word }) => {
    setOn(next.on);
    setWord(next.word);
    save.mutate(next, {
      onError: () => {
        setOn(troupe.boon_talons ?? false);
        setWord(troupe.boon_talon_word ?? "Lesser Harpies");
      },
    });
  };
  return (
    <fieldset className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <legend className="text-mist">Lesser Harpies</legend>
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending || !full} onChange={(e) => choose({ on: e.target.checked, word })} />
        <span>
          The Harpy may give others access to the ledger
          <span className="block text-xs text-mist">
            {full
              ? "The Harpy chooses who, from the troupe's player characters, and whether each may add boons, edit them and perform audits. They work from their Play View, as their character, and see what the Harpy sees."
              : "Only while the Harpy has the full ledger."}
          </span>
        </span>
      </label>
      {on && (
        <Field label="The troupe calls them">
          <Select value={word} disabled={save.isPending} onChange={(e) => choose({ on, word: e.target.value as Word })}>
            <option value="Lesser Harpies">Lesser Harpies</option>
            <option value="Talons">Talons</option>
          </Select>
        </Field>
      )}
      <ErrorText error={save.error} />
      {on && full && <StaffTalons troupeId={troupe.id} />}
    </fieldset>
  );
}

/** Who has access, for the troupe's running staff: they see it, and take it away. */
function StaffTalons({ troupeId }: { troupeId: string }) {
  const talons = useTalons(troupeId);
  if (talons.isPending) return <Loading compact />;
  if (talons.error) return <ErrorText error={talons.error} />;
  const { talons: list, word } = talons.data;
  return list.length === 0 ? (
    <p className="text-xs text-mist">The Harpy hasn&apos;t given anyone access yet.</p>
  ) : (
    <ul aria-label={word} className="flex flex-col gap-1">
      {list.map((t) => (
        <TalonRow key={t.character_id} troupeId={troupeId} talon={t} word={word} manage={false} />
      ))}
    </ul>
  );
}

function TalonRow({ troupeId, talon, word, manage }: { troupeId: string; talon: TalonOut; word: string; manage: boolean }) {
  const dates = useDates();
  const [can, setCan] = useState<Can>({
    can_add: talon.can_add,
    can_edit: talon.can_edit,
    can_audit: talon.can_audit,
  });
  const path = {
    params: { path: { troupe_id: troupeId, character_id: talon.character_id } },
  };
  const change = useAction(async (next: Can) => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/boon-talons/{character_id}", {
        ...path,
        body: next,
      }),
    );
  });
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/boon-talons/{character_id}", path));
  });
  return (
    <li className="rounded-lg border border-ash bg-dusk p-2 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p>
            <span className="text-parchment">{talon.name}</span>
            <span className="text-mist"> {what(talon)}</span>
          </p>
          <p className="text-xs text-mist">
            {talon.given_by ? `Given by ${talon.given_by}` : "Given"}, {dates.day(talon.given_at)}
            {!talon.in_play && " · Not in play in the troupe now, so without access"}
          </p>
        </div>
        <Button
          variant="ghost"
          disabled={remove.isPending}
          onClick={() => remove.mutate(undefined)}
          aria-label={`Take away ${talon.name}'s access as a ${oneOf(word)}`}
        >
          Take away
        </Button>
      </div>
      {manage && (
        <div role="group" aria-label={`What ${talon.name} may do`} className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {ABILITIES.map((a) => (
            <label key={a.key} className="flex items-center gap-2" title={a.hint}>
              <input
                type="checkbox"
                checked={can[a.key]}
                disabled={change.isPending}
                onChange={(e) => {
                  const next = { ...can, [a.key]: e.target.checked };
                  setCan(next);
                  change.mutate(next, { onError: () => setCan(can) });
                }}
              />
              {a.label}
            </label>
          ))}
        </div>
      )}
      <ErrorText error={change.error ?? remove.error} />
    </li>
  );
}

/**
 * For the Harpy, on the ledger they keep (#689): who they've given access to the
 * ledger, with what each may do, and giving it to someone new. Lesser Harpy title
 * holders are offered first. The access belongs to the office: a new Harpy finds the
 * list and keeps or removes each one.
 */
export function TalonsCard({ troupeId }: { troupeId: string }) {
  const toast = useToast();
  const talons = useTalons(troupeId);
  const [who, setWho] = useState("");
  const [can, setCan] = useState<Can>({ ...NONE, can_add: true });
  const give = useAction(async ({ id, next }: { id: string; next: Can }) => {
    const out: BoonTalonsOut = await unwrap(
      api.PUT("/api/troupes/{troupe_id}/boon-talons/{character_id}", {
        params: { path: { troupe_id: troupeId, character_id: id } },
        body: next,
      }),
    );
    const name = out.talons.find((t) => t.character_id === id)?.name ?? "They";
    toast({ message: `${name} has access to the ledger.` });
    setWho("");
  });
  if (talons.isPending) return <Loading compact />;
  if (talons.error) return <ErrorText error={talons.error} />;
  const { talons: list, choices, word } = talons.data;
  const given = new Set(list.map((t) => t.character_id));
  const open = choices.filter((c) => !given.has(c.id));
  return (
    <Card title={word}>
      <p className="mb-3 text-sm text-mist">
        Give others access to the ledger as {word}: each sees it as you do, and may add boons, edit them and perform audits, as you choose. They work from their
        Play View, as their character. Staff see who has what.
      </p>
      {list.length === 0 ? (
        <Empty>No one yet.</Empty>
      ) : (
        <ul aria-label={word} className="mb-3 flex flex-col gap-2">
          {list.map((t) => (
            <TalonRow key={t.character_id} troupeId={troupeId} talon={t} word={word} manage />
          ))}
        </ul>
      )}
      {open.length > 0 && (
        <form
          className="flex flex-col gap-2 border-t border-ash/60 pt-3 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (who) give.mutate({ id: who, next: can });
          }}
        >
          <Field label={`Make a ${oneOf(word)}`}>
            <Select value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Choose a character…</option>
              {open.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.lesser_harpy ? " (Lesser Harpy)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <div role="group" aria-label="What they may do" className="flex flex-wrap gap-x-4 gap-y-1">
            {ABILITIES.map((a) => (
              <label key={a.key} className="flex items-center gap-2" title={a.hint}>
                <input type="checkbox" checked={can[a.key]} onChange={(e) => setCan({ ...can, [a.key]: e.target.checked })} />
                {a.label}
              </label>
            ))}
          </div>
          <div>
            <Button type="submit" disabled={!who || give.isPending}>
              Give access
            </Button>
          </div>
          <ErrorText error={give.error} />
        </form>
      )}
    </Card>
  );
}
