import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card, ErrorText, Loading } from "../../components/ui";

export function XpTab({ characterId }: { characterId: string }) {
  const history = useQuery({
    queryKey: ["xp", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/xp", { params: { path: { character_id: characterId } } })),
  });
  if (history.isPending) return <Loading />;
  if (history.error) return <ErrorText error={history.error} />;
  let balance = 0;
  const rows = history.data.map((e) => ({ ...e, balance: (balance += e.amount) }));
  return (
    <Card title="Experience history">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-mist">
            <tr>
              <th className="py-2 pr-3 font-normal">Date</th>
              <th className="py-2 pr-3 font-normal">What</th>
              <th className="py-2 pr-3 text-right font-normal">XP</th>
              <th className="py-2 text-right font-normal">Balance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ash">
            {rows.reverse().map((e) => (
              <tr key={e.id}>
                <td className="py-2 pr-3 whitespace-nowrap text-mist">{e.entered_on}</td>
                <td className="py-2 pr-3">
                  {e.reason}
                  {e.kind !== "purchase" && <span className="ml-2 text-xs text-mist">{e.kind}</span>}
                </td>
                <td className={`py-2 pr-3 text-right font-mono ${e.amount < 0 ? "text-blood-bright" : "text-gold"}`}>
                  {e.amount > 0 ? `+${e.amount}` : e.amount}
                </td>
                <td className="py-2 text-right font-mono">{e.balance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
