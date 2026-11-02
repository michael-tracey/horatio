import type { ExpiryOut } from "../../api/types";
import { useDates } from "../../dates";
import { expiryText } from "../troupe/expiry";

/** When a held item expires (#443), and what happens then, on the sheet and the Play View. */
export function ExpiryLine({ expiry }: { expiry: ExpiryOut }) {
  const dates = useDates();
  return (
    <p aria-label="Expiry" className="text-xs text-gold">
      {expiryText(expiry, dates)}.{expiry.note && <span className="block text-mist">{expiry.note}</span>}
    </p>
  );
}
