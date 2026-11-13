import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../../api/client";
import { Card } from "../../../components/ui";
import { manualLink } from "../../../manualLink";

/**
 * The way into the import from Yorick (#518), which lives under Tools (#758): too
 * big for a card of its own, so the card says what it does and opens it.
 */
export function YorickImportCard() {
  const underway = useQuery({ queryKey: ["yorick-imports"], queryFn: () => unwrap(api.GET("/api/yorick-imports")) });
  const count = underway.data?.length ?? 0;

  return (
    <Card title="Import from Yorick">
      <p className="mb-3 text-sm text-mist">
        Bring a troupe's characters across from Yorick as sheeted NPCs of the troupe, from its <strong className="text-parchment">Print Characters</strong> page.{" "}
        <Link to={manualLink("custodian", "importing-characters-from-yorick")} className="text-gold hover:underline">
          How it works
        </Link>
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/custodian/tools/yorick-import" className="text-sm text-gold hover:underline">
          Open the import
        </Link>
        {count > 0 && <span className="text-sm text-mist">{count === 1 ? "1 import under way." : `${count} imports under way.`}</span>}
      </div>
    </Card>
  );
}
