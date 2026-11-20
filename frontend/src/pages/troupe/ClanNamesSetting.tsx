import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { ClanName } from "../../clanNames";
import { RadioList } from "../../components/RadioList";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

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
  const save = useSaveOnChange((assamite: ClanName) => unwrap(api.PUT("/api/troupes/{troupe_id}/clan-names", { ...path, body: { assamite } })), {
    rules: true,
    message: clanNamesChangeText,
  });
  if (!troupe.data) return null;
  const now = troupe.data.assamite_name;

  return (
    <SettingCard
      setting={SETTINGS.clanNames}
      readOnly={!canEdit}
    >
      {!canEdit ? (
        <p className="text-sm">The clan is called {now === "Banu Haqim" ? "the Banu Haqim" : "the Assamites"} here.</p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <RadioList
            label="What the clan is called"
            hideLabel
            value={now}
            options={NAMES.map((n) => ({
              value: n.value,
              label: (
                <>
                  {n.value}
                  {n.value === "Banu Haqim" && <span className="text-mist"> (the default)</span>}
                </>
              ),
              hint: n.meaning,
            }))}
            disabled={save.isPending}
            onChange={(name) => save.mutate(name)}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}
