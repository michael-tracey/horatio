import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SetupOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";

/** "1 house rule", "3 house rules". */
const houseRules = (n: number) => (n === 1 ? "1 house rule" : `${n} house rules`);

export type RuleArea = { label: string; text: string; to: string };

/**
 * The parts of the troupe's rules it plays differently from the book, a line each
 * with where it is: none when everything plays as the book has it.
 */
export function differentAreas(s: SetupOut, base: string): RuleArea[] {
  const areas: (RuleArea | false)[] = [
    s.checks > 0 && { label: "Checks", text: `${s.checks} of ${s.checks_total} played differently`, to: `${base}/house-rules/checks` },
    s.costs > 0 && { label: "Costs", text: s.costs === 1 ? "1 house price" : `${s.costs} house prices`, to: `${base}/house-rules/costs` },
    s.starting > 0 && { label: "Starting points", text: houseRules(s.starting), to: `${base}/house-rules/starting` },
    s.actions > 0 && { label: "Downtime actions", text: houseRules(s.actions), to: `${base}/house-rules/actions` },
    s.house_traits > 0 && { label: "House merits and flaws", text: `${s.house_traits} of the troupe's own`, to: `${base}/house-rules/house-traits` },
    s.other > 0 && { label: "Other house rules", text: s.other === 1 ? "1 setting unlike the book" : `${s.other} settings unlike the book`, to: `${base}/house-rules` },
  ];
  return areas.filter((a): a is RuleArea => !!a);
}

/**
 * Where the troupe plays differently from the book (#786), each linked to its part:
 * at the top of House rules for running staff, above the rules as players read them.
 * It was on the Setup tab until that joined Settings (#1048).
 */
export function PlayedDifferently({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const base = `/troupes/${troupeId}`;
  const setup = useQuery({
    queryKey: ["setup", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/setup", { params: { path: { troupe_id: troupeId } } })),
  });
  if (setup.isPending) return null;
  if (setup.error) return <ErrorText error={setup.error} />;
  const areas = differentAreas(setup.data, base);
  return (
    <Card title="Played differently from the book">
      {areas.length === 0 ? (
        <p className="text-sm text-mist">
          Everything plays as the book has it.{" "}
          <Link to={`${base}/house-rules/checks`} className="underline hover:text-parchment">
            {canEdit ? "Change what you play differently" : "See the rules"}
          </Link>
          .
        </p>
      ) : (
        <ul aria-label="Played differently" className="flex flex-col divide-y divide-ash text-sm">
          {areas.map((a) => (
            <li key={a.label}>
              <Link to={a.to} className="flex flex-wrap items-baseline justify-between gap-x-3 py-2 hover:text-gold">
                <span className="text-parchment">{a.label}</span>
                <span className="text-mist">{a.text}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
