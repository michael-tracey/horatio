import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { Card } from "../components/ui";
import { useDates } from "../dates";

/** On the person's account page: each time the custodian viewed Horatio as them,
 * and why. Shows nothing if the custodian never has. */
export function ViewedAs() {
  const visits = useQuery({ queryKey: ["viewed-as"], queryFn: () => unwrap(api.GET("/api/account/viewed-as")) });
  const dates = useDates();
  if (!visits.data?.length) return null;
  return (
    <Card title="When the custodian viewed as you">
      <p className="mb-2 text-sm text-mist">To help with a question, the custodian can see Horatio as you see it, read-only, for up to 30 minutes.</p>
      <ul className="divide-y divide-ash/50 text-sm">
        {visits.data.map((v) => (
          <li key={v.started_at} className="py-2">
            <span>
              {dates.dateTime(v.started_at)} to {dates.time(v.until)}, by {v.custodian}
            </span>
            <span className="block text-mist">{v.reason}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
