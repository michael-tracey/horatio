import { useNavigate, useParams } from "react-router";
import { usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { useTitle } from "../title";
import { SettingDocument, useSetting } from "./troupe/SettingDocument";

/**
 * A troupe's Setting Style Document, black on white, for the Storyteller table and for
 * handing to players (MET: VTM p. 331): anyone who may read it may print it.
 */
export function SettingPrintPage() {
  const { troupeId = "" } = useParams();
  const navigate = useNavigate();
  const paper = usePreferences().paper;
  const setting = useSetting(troupeId);
  useTitle(setting.data ? `Print · Setting · ${setting.data.troupe}` : "Print");
  if (setting.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (setting.error) return <p className="p-8 text-black">{setting.error.message}</p>;
  const width = { maxWidth: `${PAPERS[paper].width}in` };
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <style>{pageRule(paper, "0.5in")}</style>
      <div className="mx-auto mb-4 flex items-center justify-between gap-4 px-4 print:hidden" style={width}>
        <button onClick={() => navigate(-1)} className="text-sm underline">
          ← Back
        </button>
        <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
          Print
        </button>
      </div>
      <main className="mx-auto bg-white p-4 shadow sm:p-[0.5in] print:p-0 print:shadow-none" style={width}>
        <p className="mb-2 text-xs tracking-wide uppercase">Setting Style Document · {setting.data.troupe}</p>
        <SettingDocument setting={setting.data} print />
      </main>
    </div>
  );
}
