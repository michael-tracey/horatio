import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { ClanName } from "../../clanNames";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

const NAMES: { value: ClanName; meaning: string }[] = [
  { value: "Banu Haqim", meaning: "The clan's name in later World of Darkness books: Banu Haqim: Vizier, Kiss of the Asp (Banu Haqim)." },
  { value: "Assamite", meaning: "The name in the 2013 MET books Horatio follows: Assamite: Vizier, Kiss of the Asp (Assamite)." },
];

/** What a change did, for the toast. */
export function clanNamesChangeText(name: ClanName): string {
  return name === "Banu Haqim" ? "The clan is called the Banu Haqim here now." : "The clan is called the Assamites here now.";
}

/**
 * What the troupe calls the clan the books call the Assamites: Banu Haqim, the default
 * for a new troupe, or Assamite. Only the name shown changes, on every screen in the
 * troupe; the rules and the sheets stay as they are.
 */
export function ClanNamesSetting({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const toast = useToast();
  const save = useAction(async (assamite: ClanName) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/clan-names", { ...path, body: { assamite } }));
    toast({ message: clanNamesChangeText(assamite) });
  });
  if (!troupe.data) return null;
  const now = troupe.data.assamite_name;

  return (
    <Card title="Banu Haqim or Assamite">
      <p className="mb-3 text-sm text-mist">
        What Horatio calls the clan of Haqim on every screen here: sheets, the Play View, creation, the roster, the Who's Who and the rules. Only the name shown changes;
        the rules and the sheets are the same either way.
      </p>
      {!canEdit ? (
        <p className="text-sm">The clan is called {now === "Banu Haqim" ? "the Banu Haqim" : "the Assamites"} here.</p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <fieldset className="flex flex-col gap-2" disabled={save.isPending}>
            <legend className="sr-only">What the clan is called</legend>
            {NAMES.map((n) => (
              <label key={n.value} className="flex items-start gap-2">
                <input type="radio" name="assamite-name" className="mt-1" checked={now === n.value} onChange={() => save.mutate(n.value)} />
                <span>
                  {n.value}
                  {n.value === "Banu Haqim" && <span className="text-mist"> (the default)</span>}
                  <span className="block text-xs text-mist">{n.meaning}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
