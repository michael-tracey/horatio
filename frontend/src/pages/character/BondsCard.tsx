import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { BOND_PAGE, levelName, levelText } from "../../bonds";
import { InfoButton } from "../../components/InfoButton";
import { Button, Card } from "../../components/ui";
import { BondReportList, ReportDrinkForm } from "./BondReports";

/**
 * The character's blood bonds still felt, as the viewer may know them: those it is
 * bound by, with what each does, and those bound to it that its player has been told
 * of. Running staff see every one, with a link to the troupe's Bonds screen. Where the
 * troupe lets players report drinks (#661), its player reports one here, and sees the
 * drinks they reported and those waiting on them to confirm. Shown only when there is
 * something to show, and never while the troupe doesn't track bonds.
 */
export function BondsCard({ characterId, name, mine }: { characterId: string; name: string; mine: boolean }) {
  const bonds = useQuery({
    queryKey: ["bonds", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/bonds", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
  const [reporting, setReporting] = useState(false);
  const b = bonds.data;
  const reports = b?.reports ?? [];
  const troupes = b?.report_to ?? [];
  if (!b || (b.bound_to.length === 0 && b.bound_by.length === 0 && !b.manage_troupe_id && reports.length === 0 && troupes.length === 0)) return null;
  return (
    <Card
      dense
      title="Blood bonds"
      info={
        <InfoButton label="About blood bonds">
          <span className="block">
            Drinking a vampire&apos;s blood on separate nights binds the drinker to them: a first drink, a second, then a full bond, which wipes away every
            lesser bond.
          </span>
          <span className="mt-1 block text-mist">{BOND_PAGE}</span>
        </InfoButton>
      }
    >
      {b.bound_to.length > 0 && (
        <ul aria-label="Bound to" className="flex flex-col gap-2 text-sm">
          {b.bound_to.map((bond) => {
            const text = levelText(bond.level);
            return (
              <li key={bond.id}>
                <span className="text-parchment">Bound to {bond.name}</span>
                <span className="block">{text.line}</span>
                <span className="block text-xs text-mist">{text.effect}</span>
              </li>
            );
          })}
        </ul>
      )}
      {b.bound_by.length > 0 && (
        <div className={b.bound_to.length > 0 ? "mt-3 border-t border-ash pt-2" : ""}>
          <p className="text-xs tracking-wide text-mist uppercase">{mine ? "Bound to you" : `Bound to ${name}`}</p>
          <ul aria-label={mine ? "Bound to you" : `Bound to ${name}`} className="mt-1 flex flex-col gap-1 text-sm">
            {b.bound_by.map((bond) => (
              <li key={bond.id}>
                {bond.name}: <span className="text-mist">{levelName(bond.level).toLowerCase()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {b.bound_to.length === 0 && b.bound_by.length === 0 && <p className="text-sm text-mist">No blood bonds recorded.</p>}
      {reports.length > 0 && (
        <div className="mt-3 border-t border-ash pt-2">
          <p className="mb-1 text-xs tracking-wide text-mist uppercase">Drinks reported</p>
          <BondReportList characterId={characterId} reports={reports} />
        </div>
      )}
      {troupes.length > 0 && (
        <div className="mt-3">
          {reporting ? (
            <ReportDrinkForm characterId={characterId} name={name} troupes={troupes} onDone={() => setReporting(false)} />
          ) : (
            <Button variant="secondary" onClick={() => setReporting(true)}>
              Report a drink
            </Button>
          )}
        </div>
      )}
      {b.manage_troupe_id && (
        <p className="mt-2 text-sm">
          <Link to={`/troupes/${b.manage_troupe_id}/bonds`} className="text-mist underline hover:text-parchment">
            Bonds screen
          </Link>
        </p>
      )}
    </Card>
  );
}
