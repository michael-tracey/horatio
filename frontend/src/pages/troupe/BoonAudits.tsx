import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { BoonAuditSummaryOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

function useAudits(troupeId: string) {
  return useQuery({
    queryKey: ["boon-audits", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-audits", { params: { path: { troupe_id: troupeId } } })),
  });
}

/**
 * Audits of a character's boons (#690), in the ledger: make one, as the ledger holds
 * their boons now and kept as it is, and give it to a player character, whose player
 * reads it in the Play View. For the troupe's staff, its Harpy with the full ledger,
 * and Lesser Harpies the Harpy let perform audits (`inPlay`: as their character).
 * Staff see every audit; a Harpy or Lesser Harpy those made in play.
 */
export function AuditsCard({ troupeId, inPlay = false }: { troupeId: string; inPlay?: boolean }) {
  const audits = useAudits(troupeId);
  const toast = useToast();
  const [subject, setSubject] = useState("");
  const [givenTo, setGivenTo] = useState("");
  const make = useAction(
    async () => {
      const made = await unwrap(
        api.POST("/api/troupes/{troupe_id}/boon-audits", {
          params: { path: { troupe_id: troupeId } },
          body: { character_id: subject, given_to_id: givenTo || null },
        }),
      );
      toast({ message: made.given_to ? `Audited ${made.name}'s boons, and gave it to ${made.given_to}.` : `Audited ${made.name}'s boons.` });
      setSubject("");
      setGivenTo("");
    },
    [["boon-audits", troupeId]],
  );

  return (
    <Card title="Audits">
      <p className="text-sm text-mist">
        An audit is one character&apos;s boons as the ledger holds them now, kept as they are: later changes don&apos;t alter it. It leaves out staff notes and logs, and
        shows who has left only as the court knows it (the Who&apos;s Who). Give it to a character, and their player reads it in the Play View.
        {inPlay && " What you do here is logged as your character."}
      </p>
      {audits.isPending ? (
        <Loading compact />
      ) : audits.error ? (
        <ErrorText error={audits.error} />
      ) : (
        <>
          {audits.data.can_audit && (
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <Field label="Audit">
                <Select value={subject} onChange={(e) => setSubject(e.target.value)}>
                  <option value="">Choose a character…</option>
                  {audits.data.subjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Give it to">
                <Select value={givenTo} onChange={(e) => setGivenTo(e.target.value)}>
                  <option value="">No one yet</option>
                  {audits.data.recipients.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button disabled={!subject || make.isPending} onClick={() => make.mutate(undefined)}>
                Make the audit
              </Button>
            </div>
          )}
          <ErrorText error={make.error} />
          {audits.data.audits.length === 0 ? (
            <Empty>No audits yet.</Empty>
          ) : (
            <ul aria-label="Audits" className="mt-3 flex flex-col divide-y divide-ash/60">
              {audits.data.audits.map((a) => (
                <AuditRow key={a.id} troupeId={troupeId} audit={a} recipients={audits.data.recipients} />
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

function AuditRow({ troupeId, audit, recipients }: { troupeId: string; audit: BoonAuditSummaryOut; recipients: { id: string; name: string }[] }) {
  const dates = useDates();
  const toast = useToast();
  const [to, setTo] = useState("");
  const give = useAction(
    async () => {
      const given = await unwrap(
        api.POST("/api/troupes/{troupe_id}/boon-audits/{audit_id}/give", {
          params: { path: { troupe_id: troupeId, audit_id: audit.id } },
          body: { character_id: to },
        }),
      );
      toast({ message: `Gave ${given.given_to} the audit of ${given.name}'s boons.` });
    },
    [["boon-audits", troupeId]],
  );
  return (
    <li className="flex flex-col gap-2 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm">
        <Link to={`/print/boon-audits/${audit.id}`} className="font-medium text-parchment underline hover:text-gold">
          {audit.name}
        </Link>
        <span className="block text-xs text-mist">
          {dates.date(audit.made_at)} · by {audit.made_by}
          {audit.given_to && ` · given to ${audit.given_to}`}
        </span>
      </div>
      {audit.can_give && (
        <div className="flex items-center gap-2">
          <Select aria-label={`Give the audit of ${audit.name} to`} value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Give it to…</option>
            {recipients.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
          <Button variant="secondary" disabled={!to || give.isPending} onClick={() => give.mutate(undefined)}>
            Give
          </Button>
        </div>
      )}
      <ErrorText error={give.error} />
    </li>
  );
}
