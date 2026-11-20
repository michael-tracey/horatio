import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { RadioList } from "../../components/RadioList";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

type Setting = "leave" | "remove" | "keep_xp";

const OPTIONS: { value: Setting; label: string; meaning: string }[] = [
  {
    value: "leave",
    label: "Leave the flaw",
    meaning: "It stays on the sheet, and staff see a warning on the diablerie form.",
  },
  {
    value: "remove",
    label: "Remove the flaw and the XP it gave",
    meaning: "It comes off, and a correction line in the XP history takes back what it gave (as far as the character has the XP).",
  },
  {
    value: "keep_xp",
    label: "Remove the flaw and keep the XP",
    meaning: "It comes off, and the XP it gave stays with the character.",
  },
];

/** House rule: what recording a diablerie does to a Lesser Generation or Thin Blooded flaw its holder has. Saved as it is chosen. */
export function DiablerieFlaws({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const save = useSaveOnChange((setting: Setting) => unwrap(api.PUT("/api/troupes/{troupe_id}/diablerie-flaws", { ...path, body: { setting } })), { rules: true });
  if (!troupe.data) return null;
  const now = troupe.data.diablerie_flaws as Setting;
  const current = OPTIONS.find((o) => o.value === now) ?? OPTIONS[0]!;
  return (
    <SettingCard
      setting={SETTINGS.diablerie}
      readOnly={!canEdit}
    >
      {!canEdit ? (
        <p className="text-sm">
          {current.label}. <span className="text-mist">{current.meaning}</span>
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <RadioList
            label="What diablerie does to Lesser Generation"
            hideLabel
            value={now}
            options={OPTIONS.map((o) => ({ value: o.value, label: o.label, hint: o.meaning }))}
            disabled={save.isPending}
            onChange={(setting) => save.mutate(setting)}
          />
          <ErrorText error={save.error} />
        </div>
      )}
    </SettingCard>
  );
}
