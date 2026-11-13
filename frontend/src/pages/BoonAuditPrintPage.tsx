import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { BoonAuditOut } from "../api/types";
import { auditCounts, auditWho, lineStatus, type AuditLine } from "../boonAudits";
import { kindName } from "../boons";
import { useDates } from "../dates";
import { usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { useTitle } from "../title";

/**
 * An audit of a character's boons (#690), as it was made, black on white: for the
 * player of the character it was given to (from the Play View's Boons tab), and for
 * whoever keeps the ledger. Readable on a phone; printable on the person's paper.
 */
export function BoonAuditPrintPage() {
  const { auditId = "" } = useParams();
  const navigate = useNavigate();
  const paper = usePreferences().paper;
  const dates = useDates();
  const audit = useQuery({
    queryKey: ["boon-audit", auditId],
    queryFn: () => unwrap(api.GET("/api/boon-audits/{audit_id}", { params: { path: { audit_id: auditId } } })),
  });
  useTitle(audit.data ? `Print · Boon audit · ${audit.data.name}` : "Print");
  if (audit.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (audit.error) return <p className="p-8 text-black">{audit.error.message}</p>;
  const a = audit.data;
  const width = { maxWidth: `${PAPERS[paper].width}in` };
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <style>{pageRule(paper, "0.45in")}</style>
      <div className="mx-auto mb-4 flex items-center justify-between gap-4 px-4 print:hidden" style={width}>
        <button onClick={() => navigate(-1)} className="text-sm underline">
          ← Back
        </button>
        <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
          Print
        </button>
      </div>
      <main className="mx-auto bg-white p-4 shadow sm:p-[0.45in] print:p-0 print:shadow-none" style={width}>
        <h1 className="font-display text-2xl">Boon audit · {a.name}</h1>
        <p className="text-sm">{auditWho(a)}</p>
        <p className="mt-1 text-sm">
          As the ledger of {a.troupe_name} stood on {dates.date(a.made_at)} · audited by {a.made_by}
          {a.given_to && ` · for ${a.given_to}`}
        </p>
        <p className="mt-2 font-semibold">{auditCounts(a)}</p>
        <Side title={`Boons ${a.name} owes`} lines={a.owes} who="Owed to" />
        <Side title={`Boons owed to ${a.name}`} lines={a.owed} who="Owed by" />
      </main>
    </div>
  );
}

function Side({ title, lines, who }: { title: string; lines: BoonAuditOut["owes"]; who: string }) {
  const dates = useDates();
  return (
    <section aria-label={title} className="mt-5 break-inside-auto">
      <h2 className="mb-1 border-b border-black text-lg font-semibold break-after-avoid">{title}</h2>
      {lines.length === 0 ? (
        <p className="text-sm">None.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[32rem] text-left text-[9pt] leading-snug">
            <thead>
              <tr className="border-b border-neutral-400">
                <th className="py-1 pr-2">{who}</th>
                <th className="py-1 pr-2">Kind</th>
                <th className="py-1 pr-2">Night</th>
                <th className="py-1 pr-2">Reason</th>
                <th className="py-1 pr-2">Stipulations</th>
                <th className="py-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line: AuditLine, n) => (
                <tr key={n} className="border-b border-neutral-200 align-top break-inside-avoid">
                  <td className="py-1 pr-2">{line.other}</td>
                  <td className="py-1 pr-2">{kindName(line.kind)}</td>
                  <td className="py-1 pr-2 whitespace-nowrap">{dates.day(line.made_on)}</td>
                  <td className="py-1 pr-2">{line.reason}</td>
                  <td className="py-1 pr-2">{line.conditions}</td>
                  <td className="py-1">{lineStatus(line)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
