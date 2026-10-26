import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Dialog } from "../../components/Dialog";
import { Badge } from "../../components/ui";
import { RulesCard } from "../troupe/StockNpcBuilder";

/** The NPC kinds the server has, once for the whole app. */
export function useNpcKinds() {
  return useQuery({ queryKey: ["npc-kinds"], queryFn: () => unwrap(api.GET("/api/npc-kinds")), staleTime: Infinity });
}

/**
 * The name of a sheeted NPC's kind as a badge, with its rules card one tap away
 * (MET: VTM ch. 12). A plain vampire is the sheet as it stands, so it gets neither.
 */
export function KindBadge({ kind, name }: { kind: string | null; name: string | null }) {
  const [open, setOpen] = useState(false);
  const kinds = useNpcKinds();
  if (!kind || kind === "vampire") return null;
  const found = kinds.data?.find((k) => k.key === kind);
  return (
    <>
      <Badge tone="gold">{name ?? found?.name ?? kind}</Badge>
      {found && (
        <button type="button" className="text-sm text-gold underline hover:text-parchment" onClick={() => setOpen(true)}>
          Rules card
        </button>
      )}
      {found && (
        <Dialog title="Rules card" open={open} onClose={() => setOpen(false)}>
          <RulesCard kind={{ ...found, name: name ?? found.name }} />
        </Dialog>
      )}
    </>
  );
}
