import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { Toggle } from "../../components/Toggle";
import { ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * Whether you are told of each boon a player reports (#1018): a notification in your bell,
 * linking to To review while the boon waits there. Your own choice, never the troupe's.
 * `as` "staff": in the Boons settings, off until you turn it on. `as` "keeper": the Harpy,
 * or a Lesser Harpy who approves reported boons, on their ledger's To review tab, on until
 * they turn it off. Shown only to those who have the choice. Account › Notifications shows
 * the same switch for each troupe (#1053), named by `label`, so the choice is kept in one place.
 */
export function ToldOfReports({ troupeId, as, label, hint }: { troupeId: string; as: "staff" | "keeper"; label?: string; hint?: string }) {
  const toast = useToast();
  const client = useQueryClient();
  const key = ["boon-reports-told", troupeId];
  const told = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-reports-told", { params: { path: { troupe_id: troupeId } } })),
  });
  // Shown as chosen at once, while it saves.
  const [chosen, setChosen] = useState<boolean | null>(null);
  const save = useAction(
    async (on: boolean) => {
      const done = await unwrap(
        api.PUT("/api/troupes/{troupe_id}/boon-reports-told", { params: { path: { troupe_id: troupeId } }, body: { on, role: as } }),
      );
      client.setQueryData(key, done);
      toast({ message: on ? "You'll be told when a player reports a boon." : "You won't be told when a player reports a boon." });
    },
    [],
    { answered: [key] },
  );
  const saved = told.data?.[as];
  if (saved === null || saved === undefined) return null;
  return (
    <div className={label ? "text-sm" : as === "staff" ? "mt-3 border-t border-ash/60 pt-3 text-sm" : "text-sm"}>
      <Toggle
        label={label ?? "Tell me when a player reports a boon"}
        hint={
          hint ??
          (as === "staff"
            ? "Just for you, not a troupe setting: a notification for each boon players report, linking to To review while it waits there."
            : "Just for you: a notification for each boon players report, linking here while it waits for review.")
        }
        checked={chosen ?? saved}
        disabled={save.isPending}
        onChange={(on) => {
          setChosen(on);
          save.mutate(on, { onSettled: () => setChosen(null) });
        }}
      />
      <ErrorText error={save.error} />
    </div>
  );
}
